# Qwen-Image-2512 API Service

OpenAI-compatible image generation API powered by [Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512), optimized for NVIDIA Jetson Thor.

## Features

- **OpenAI-compatible API** - Drop-in replacement for DALL-E endpoints
- **Job queue system** - Queue up to 5 concurrent requests with real-time status updates
- **WebSocket updates** - Live progress tracking during generation
- **Web UI** - Built-in frontend for submitting prompts and viewing results
- **Multiple aspect ratios** - Support for 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3
- **Subprocess isolation** - Each generation runs in isolated subprocess for GPU memory cleanup

## Quick Start

### Prerequisites

- NVIDIA Jetson Thor (or other Jetson with sufficient VRAM)
- Docker with NVIDIA runtime
- Model weights at `/data/models/Qwen-Image-2512`

### Run with Docker

```bash
docker build -t qwenimage:jetson .

docker run -d --name qwenimage --runtime nvidia \
  -p 8002:8002 \
  -e DEVICE=cuda \
  -v /data/models:/data/models \
  qwenimage:jetson
```

### Access

- **Web UI**: http://localhost:8002
- **API**: http://localhost:8002/v1/images/generations

## API Reference

### Generate Images

```bash
curl -X POST http://localhost:8002/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A serene mountain landscape at sunrise",
    "size": "1024x1024",
    "n": 1
  }'
```

**Request Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | required | Text description of the image |
| `n` | int | 1 | Number of images (1-4) |
| `size` | string | "1024x1024" | Image size: 1024x1024, 1792x1024, 1024x1792 |
| `aspect_ratio` | string | null | Override size with ratio: 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3 |
| `num_inference_steps` | int | 50 | Denoising steps (1-100) |
| `guidance_scale` | float | 4.0 | CFG scale (1.0-20.0) |
| `response_format` | string | "b64_json" | Response format: b64_json or url |

**Response:**

```json
{
  "job_id": "abc12345",
  "status": "queued",
  "position": 2,
  "message": "Job queued at position 2. Poll /v1/jobs/abc12345 for status."
}
```

### Check Job Status

```bash
curl http://localhost:8002/v1/jobs/{job_id}
```

**Response (running):**
```json
{
  "job_id": "abc12345",
  "status": "running",
  "progress": 45,
  "current_step": 23,
  "eta_seconds": 12.5
}
```

**Response (completed):**
```json
{
  "job_id": "abc12345",
  "status": "completed",
  "result": {
    "created": 1704067200,
    "data": [{"b64_json": "..."}]
  }
}
```

### Get Queue Status

```bash
curl http://localhost:8002/v1/queue
```

### List Aspect Ratios

```bash
curl http://localhost:8002/v1/aspect_ratios
```

### WebSocket (Real-time Updates)

Connect to `ws://localhost:8002/ws` for live queue and progress updates.

## Web UI

The built-in web interface provides:

- Prompt input with aspect ratio selection
- Real-time job queue monitoring
- Image gallery with fullscreen viewer
- Toggle between "My Jobs" and "All Jobs" views
- Automatic image storage (last 30 images)

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PORT` | 8002 | Server port |
| `DEVICE` | cuda | Device (cuda/cpu) |
| `MODEL_PATH` | /data/models/Qwen-Image-2512 | Path to model weights |
| `HF_HOME` | /models | Hugging Face cache directory |

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│  FastAPI    │────▶│  Job Queue  │
│  (Web/API)  │◀────│  Server     │◀────│  (asyncio)  │
└─────────────┘     └─────────────┘     └─────────────┘
      │                   │                    │
      │              WebSocket            Subprocess
      │              Updates              Generation
      │                   │                    │
      ▼                   ▼                    ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │     │  Broadcast  │     │  GPU/CUDA   │
│  (IndexedDB)│     │  Manager    │     │  Isolated   │
└─────────────┘     └─────────────┘     └─────────────┘
```

## License

MIT
