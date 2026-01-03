"""
Qwen-Image-2512 API Server - OpenAI-compatible image generation API with job queue
"""

import os
import io
import base64
import time
import uuid
import asyncio
from enum import Enum
from typing import Optional, Literal, Dict, List
from contextlib import asynccontextmanager
from collections import OrderedDict

import torch
from PIL import Image
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json

# Configuration
MAX_QUEUE_SIZE = 5
RESULT_TTL_SECONDS = 300  # 5 minutes

# Global pipeline
pipe = None

# Job status enum
class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

# Job storage
jobs: Dict[str, dict] = OrderedDict()
job_queue: asyncio.Queue = None
current_job_id: Optional[str] = None
worker_task: asyncio.Task = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            print("No active connections to broadcast to")
            return

        data = json.dumps(message)
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_text(data)
                print(f"Sent message to client")
            except Exception as e:
                print(f"Failed to send to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected
        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()

MODEL_ID = "Qwen/Qwen-Image-2512"
MODEL_PATH = os.getenv("MODEL_PATH", "/data/models/Qwen-Image-2512")
DEVICE = os.getenv("DEVICE", "cuda")

# Supported aspect ratios and their dimensions
ASPECT_RATIOS = {
    "1:1": (1024, 1024),
    "16:9": (1664, 928),
    "9:16": (928, 1664),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
    "3:2": (1248, 832),
    "2:3": (832, 1248),
}

# Map OpenAI sizes to aspect ratios
SIZE_MAP = {
    "1024x1024": "1:1",
    "1792x1024": "16:9",
    "1024x1792": "9:16",
}


class ImageGenerationRequest(BaseModel):
    model: str = MODEL_ID
    prompt: str
    n: int = Field(default=1, ge=1, le=4)
    size: Optional[str] = "1024x1024"
    aspect_ratio: Optional[str] = None
    response_format: Literal["url", "b64_json"] = "b64_json"
    num_inference_steps: int = Field(default=50, ge=1, le=100)
    guidance_scale: float = Field(default=4.0, ge=1.0, le=20.0)


class ImageData(BaseModel):
    b64_json: Optional[str] = None
    url: Optional[str] = None
    revised_prompt: Optional[str] = None


class ImageGenerationResponse(BaseModel):
    created: int
    data: list[ImageData]


class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    position: int
    message: str


def image_to_base64(image: Image.Image) -> str:
    """Convert PIL Image to base64 string."""
    # Force image data to be fully loaded
    image.load()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def create_job(request: ImageGenerationRequest) -> dict:
    """Create a new job entry."""
    job_id = str(uuid.uuid4())[:8]

    # Determine dimensions
    if request.aspect_ratio and request.aspect_ratio in ASPECT_RATIOS:
        width, height = ASPECT_RATIOS[request.aspect_ratio]
    elif request.size and request.size in SIZE_MAP:
        ratio = SIZE_MAP[request.size]
        width, height = ASPECT_RATIOS[ratio]
    else:
        width, height = ASPECT_RATIOS["1:1"]

    return {
        "job_id": job_id,
        "status": JobStatus.QUEUED,
        "prompt": request.prompt,
        "width": width,
        "height": height,
        "num_inference_steps": request.num_inference_steps,
        "guidance_scale": request.guidance_scale,
        "n": request.n,
        "response_format": request.response_format,
        "created_at": time.time(),
        "started_at": None,
        "completed_at": None,
        "progress": 0,
        "current_step": 0,
        "total_steps": request.num_inference_steps,
        "estimated_remaining": None,
        "result": None,
        "error": None,
    }


def get_queue_position(job_id: str) -> int:
    """Get position of job in queue (1-indexed), 0 if running, -1 if not queued."""
    if job_id == current_job_id:
        return 0

    position = 1
    for jid, job in jobs.items():
        if job["status"] == JobStatus.QUEUED:
            if jid == job_id:
                return position
            position += 1
    return -1


def cleanup_old_jobs():
    """Remove completed/failed jobs older than TTL."""
    now = time.time()
    to_remove = []

    for job_id, job in jobs.items():
        if job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
            if job["completed_at"] and (now - job["completed_at"]) > RESULT_TTL_SECONDS:
                to_remove.append(job_id)

    for job_id in to_remove:
        del jobs[job_id]


def build_queue_status() -> dict:
    """Build queue status dict for broadcasting."""
    running = None
    queued = []
    recent_completed = []

    for job_id, job in jobs.items():
        job_info = {
            "job_id": job["job_id"],
            "prompt": job["prompt"][:100] + "..." if len(job["prompt"]) > 100 else job["prompt"],
            "status": job["status"].value if isinstance(job["status"], JobStatus) else job["status"],
            "created_at": job["created_at"],
        }

        if job["status"] == JobStatus.RUNNING:
            job_info["progress"] = job["progress"]
            job_info["current_step"] = job["current_step"]
            job_info["total_steps"] = job["total_steps"]
            job_info["estimated_remaining"] = job["estimated_remaining"]
            running = job_info

        elif job["status"] == JobStatus.QUEUED:
            job_info["position"] = get_queue_position(job_id)
            queued.append(job_info)

        elif job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
            job_info["completed_at"] = job["completed_at"]
            if job["status"] == JobStatus.FAILED:
                job_info["error"] = job["error"]
            recent_completed.append(job_info)

    queued.sort(key=lambda x: x.get("position", 999))
    recent_completed.sort(key=lambda x: x.get("completed_at", 0), reverse=True)

    return {
        "type": "queue_update",
        "max_queue_size": MAX_QUEUE_SIZE,
        "running": running,
        "queued": queued,
        "recent_completed": recent_completed[:10],
    }


async def broadcast_queue_status():
    """Broadcast current queue status to all WebSocket clients."""
    status = build_queue_status()
    print(f"Broadcasting to {len(ws_manager.active_connections)} clients: {status.get('running', {}).get('job_id') if status.get('running') else 'no running job'}")
    await ws_manager.broadcast(status)


def progress_callback(pipe, step, timestep, callback_kwargs):
    """Callback to track generation progress."""
    global current_job_id, jobs

    if current_job_id and current_job_id in jobs:
        job = jobs[current_job_id]
        job["current_step"] = step + 1
        job["progress"] = int((step + 1) / job["total_steps"] * 100)

        # Estimate remaining time
        if job["started_at"] and step > 0:
            elapsed = time.time() - job["started_at"]
            time_per_step = elapsed / (step + 1)
            remaining_steps = job["total_steps"] - (step + 1)
            job["estimated_remaining"] = round(time_per_step * remaining_steps, 1)

    return callback_kwargs


def do_generation(prompt, width, height, num_inference_steps, guidance_scale, job_dict):
    """Run generation with fresh pipeline load.

    Note: Loading fresh per request is required on Jetson Thor.
    Keeping the model in memory after startup causes gray output.
    """
    from diffusers import QwenImagePipeline

    def step_callback(pipe, step, timestep, callback_kwargs):
        """Update job progress during generation."""
        job_dict["current_step"] = step + 1
        job_dict["progress"] = int((step + 1) / job_dict["total_steps"] * 100)

        # Estimate remaining time
        if job_dict["started_at"] and step > 0:
            elapsed = time.time() - job_dict["started_at"]
            time_per_step = elapsed / (step + 1)
            remaining_steps = job_dict["total_steps"] - (step + 1)
            job_dict["estimated_remaining"] = round(time_per_step * remaining_steps, 1)

        return callback_kwargs

    print(f"Loading model for generation...")
    job_dict["current_step"] = 0
    job_dict["progress"] = 0

    local_pipe = QwenImagePipeline.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        local_files_only=True,
    ).to('cuda')

    print(f"Model loaded, starting inference...")
    result = local_pipe(
        prompt=prompt,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
        true_cfg_scale=guidance_scale,
        output_type="pil",
        callback_on_step_end=step_callback,
    )
    image = result.images[0]

    # Cleanup to free memory
    del local_pipe
    torch.cuda.empty_cache()

    # Convert to PNG bytes
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def periodic_broadcast(stop_event: asyncio.Event):
    """Broadcast queue status every 2 seconds until stopped."""
    while not stop_event.is_set():
        await broadcast_queue_status()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


async def process_job(job: dict):
    """Process a single job."""
    global current_job_id

    job_id = job["job_id"]
    current_job_id = job_id
    job["status"] = JobStatus.RUNNING
    job["started_at"] = time.time()

    # Broadcast job started
    await broadcast_queue_status()

    # Start periodic broadcaster
    stop_broadcast = asyncio.Event()
    broadcast_task = asyncio.create_task(periodic_broadcast(stop_broadcast))

    try:
        images_data = []

        for i in range(job["n"]):
            job["current_step"] = 0
            job["progress"] = 0

            # Run in a separate thread to isolate from asyncio event loop
            png_bytes = await asyncio.to_thread(
                do_generation,
                job["prompt"],
                job["width"],
                job["height"],
                job["num_inference_steps"],
                job["guidance_scale"],
                job,  # Pass job dict for progress updates
            )

            images_data.append({
                "b64_json": base64.b64encode(png_bytes).decode("utf-8"),
                "revised_prompt": job["prompt"],
            })
            job["progress"] = 100

        job["status"] = JobStatus.COMPLETED
        job["completed_at"] = time.time()
        job["result"] = {
            "created": int(job["completed_at"]),
            "data": images_data,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        job["status"] = JobStatus.FAILED
        job["completed_at"] = time.time()
        job["error"] = str(e)

    finally:
        current_job_id = None
        # Stop periodic broadcaster
        stop_broadcast.set()
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass
        # Final broadcast for job completed/failed
        await broadcast_queue_status()


async def queue_worker():
    """Background worker that processes jobs from the queue."""
    global job_queue

    while True:
        try:
            # Wait for a job
            job_id = await job_queue.get()

            if job_id in jobs:
                job = jobs[job_id]
                if job["status"] == JobStatus.QUEUED:
                    await process_job(job)

            job_queue.task_done()

            # Cleanup old jobs periodically
            cleanup_old_jobs()

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Worker error: {e}")
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start worker on startup - model loaded fresh per request."""
    global job_queue, worker_task

    print(f"Server starting - model will be loaded fresh per request")

    # Initialize queue and start worker
    job_queue = asyncio.Queue()
    worker_task = asyncio.create_task(queue_worker())
    print("Job queue worker started")

    yield

    # Cleanup
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

    torch.cuda.empty_cache()


app = FastAPI(title="Qwen-Image-2512 API", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


@app.get("/")
async def root():
    """Serve frontend."""
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "model": MODEL_ID}


@app.get("/v1/models")
async def list_models():
    """List available models - includes DALL-E aliases for compatibility."""
    return {
        "object": "list",
        "data": [
            {"id": "dall-e-3", "object": "model", "created": 0, "owned_by": "openai"},
            {"id": "dall-e-2", "object": "model", "created": 0, "owned_by": "openai"},
            {"id": MODEL_ID, "object": "model", "created": 0, "owned_by": "qwen"},
        ]
    }


@app.get("/v1/status")
async def get_status():
    """Get current generation status (backward compatible)."""
    running_job = None
    if current_job_id and current_job_id in jobs:
        running_job = jobs[current_job_id]

    queued_count = sum(1 for j in jobs.values() if j["status"] == JobStatus.QUEUED)

    if running_job:
        return {
            "is_generating": True,
            "job_id": running_job["job_id"],
            "prompt": running_job["prompt"],
            "progress": running_job["progress"],
            "current_step": running_job["current_step"],
            "total_steps": running_job["total_steps"],
            "started_at": running_job["started_at"],
            "estimated_remaining": running_job["estimated_remaining"],
            "queue_length": queued_count,
        }
    else:
        return {
            "is_generating": False,
            "job_id": None,
            "prompt": None,
            "progress": 0,
            "current_step": 0,
            "total_steps": 0,
            "started_at": None,
            "estimated_remaining": None,
            "queue_length": queued_count,
        }


@app.get("/v1/queue")
async def get_queue():
    """Get full queue status."""
    running = None
    queued = []
    recent_completed = []

    for job_id, job in jobs.items():
        job_info = {
            "job_id": job["job_id"],
            "prompt": job["prompt"][:100] + "..." if len(job["prompt"]) > 100 else job["prompt"],
            "status": job["status"],
            "created_at": job["created_at"],
        }

        if job["status"] == JobStatus.RUNNING:
            job_info["progress"] = job["progress"]
            job_info["current_step"] = job["current_step"]
            job_info["total_steps"] = job["total_steps"]
            job_info["estimated_remaining"] = job["estimated_remaining"]
            running = job_info

        elif job["status"] == JobStatus.QUEUED:
            job_info["position"] = get_queue_position(job_id)
            queued.append(job_info)

        elif job["status"] in (JobStatus.COMPLETED, JobStatus.FAILED):
            job_info["completed_at"] = job["completed_at"]
            if job["status"] == JobStatus.FAILED:
                job_info["error"] = job["error"]
            recent_completed.append(job_info)

    # Sort queued by position
    queued.sort(key=lambda x: x.get("position", 999))
    # Sort completed by completion time (newest first)
    recent_completed.sort(key=lambda x: x.get("completed_at", 0), reverse=True)

    return {
        "max_queue_size": MAX_QUEUE_SIZE,
        "running": running,
        "queued": queued,
        "recent_completed": recent_completed[:10],  # Last 10
    }


@app.get("/v1/jobs/{job_id}")
async def get_job(job_id: str):
    """Get status of a specific job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    response = {
        "job_id": job["job_id"],
        "status": job["status"],
        "prompt": job["prompt"],
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "progress": job["progress"],
        "current_step": job["current_step"],
        "total_steps": job["total_steps"],
        "estimated_remaining": job["estimated_remaining"],
        "error": job["error"],
    }

    if job["status"] == JobStatus.QUEUED:
        response["position"] = get_queue_position(job_id)

    # Include result if completed
    if job["status"] == JobStatus.COMPLETED and job["result"]:
        response["result"] = job["result"]

    return response


@app.delete("/v1/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a queued job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    if job["status"] != JobStatus.QUEUED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status: {job['status']}"
        )

    job["status"] = JobStatus.FAILED
    job["completed_at"] = time.time()
    job["error"] = "Cancelled by user"

    return {"message": "Job cancelled", "job_id": job_id}


@app.post("/v1/images/generations")
async def generate_images(request: ImageGenerationRequest):
    """Submit image generation job to queue."""
    global job_queue

    # Check queue size
    queued_count = sum(1 for j in jobs.values() if j["status"] == JobStatus.QUEUED)
    if queued_count >= MAX_QUEUE_SIZE:
        raise HTTPException(
            status_code=503,
            detail=f"Queue full ({MAX_QUEUE_SIZE} jobs). Try again later."
        )

    # Create and store job
    job = create_job(request)
    jobs[job["job_id"]] = job

    # Add to queue
    await job_queue.put(job["job_id"])

    position = get_queue_position(job["job_id"])

    # Broadcast new job added
    await broadcast_queue_status()

    return JobSubmitResponse(
        job_id=job["job_id"],
        status=job["status"],
        position=position,
        message=f"Job queued at position {position}. Poll /v1/jobs/{job['job_id']} for status.",
    )


@app.get("/v1/aspect_ratios")
async def list_aspect_ratios():
    """List supported aspect ratios."""
    return {
        "aspect_ratios": ASPECT_RATIOS,
        "size_map": SIZE_MAP,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await ws_manager.connect(websocket)

    # Send initial queue status
    status = build_queue_status()
    await websocket.send_text(json.dumps(status))

    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Client can send "ping" to keep alive
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
