# Qwen-Image-2512 API Documentation

Base URL: `http://localhost:8002`

## Overview

This API is OpenAI-compatible and can be used as a drop-in replacement for DALL-E endpoints. Jobs are queued and processed sequentially with real-time progress updates via WebSocket.

## Authentication

No authentication required for local deployment.

---

## Endpoints

### Generate Images

Submit an image generation request to the queue.

```
POST /v1/images/generations
```

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | Yes | - | Text description of the image to generate |
| `model` | string | No | `Qwen/Qwen-Image-2512` | Model ID (ignored, for compatibility) |
| `n` | integer | No | 1 | Number of images to generate (1-4) |
| `size` | string | No | `1024x1024` | Image size (see Size Options) |
| `aspect_ratio` | string | No | null | Override size with aspect ratio (see Aspect Ratios) |
| `num_inference_steps` | integer | No | 50 | Number of denoising steps (1-100) |
| `guidance_scale` | float | No | 4.0 | Classifier-free guidance scale (1.0-20.0) |
| `response_format` | string | No | `b64_json` | Response format: `b64_json` or `url` |

#### Size Options

| Size | Aspect Ratio |
|------|--------------|
| `1024x1024` | 1:1 |
| `1792x1024` | 16:9 |
| `1024x1792` | 9:16 |

#### Aspect Ratios

| Ratio | Dimensions |
|-------|------------|
| `1:1` | 1024 × 1024 |
| `16:9` | 1664 × 928 |
| `9:16` | 928 × 1664 |
| `4:3` | 1152 × 864 |
| `3:4` | 864 × 1152 |
| `3:2` | 1248 × 832 |
| `2:3` | 832 × 1248 |

#### Example Request

```bash
curl -X POST http://localhost:8002/v1/images/generations \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A cyberpunk city with flying cars and neon signs",
    "size": "1024x1024",
    "num_inference_steps": 50,
    "guidance_scale": 4.0
  }'
```

#### Response

```json
{
  "job_id": "a1b2c3d4",
  "status": "queued",
  "position": 1,
  "message": "Job queued at position 1. Poll /v1/jobs/a1b2c3d4 for status."
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 503 | Queue full (max 5 jobs) |

---

### Get Job Status

Retrieve the status and result of a specific job.

```
GET /v1/jobs/{job_id}
```

#### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | The job ID returned from generation request |

#### Example Request

```bash
curl http://localhost:8002/v1/jobs/a1b2c3d4
```

#### Response (Queued)

```json
{
  "job_id": "a1b2c3d4",
  "status": "queued",
  "prompt": "A cyberpunk city with flying cars and neon signs",
  "position": 2,
  "created_at": 1704067200.123,
  "started_at": null,
  "completed_at": null,
  "progress": 0,
  "current_step": 0,
  "total_steps": 50,
  "estimated_remaining": null,
  "error": null
}
```

#### Response (Running)

```json
{
  "job_id": "a1b2c3d4",
  "status": "running",
  "prompt": "A cyberpunk city with flying cars and neon signs",
  "created_at": 1704067200.123,
  "started_at": 1704067205.456,
  "completed_at": null,
  "progress": 45,
  "current_step": 23,
  "total_steps": 50,
  "estimated_remaining": 12.5,
  "error": null
}
```

#### Response (Completed)

```json
{
  "job_id": "a1b2c3d4",
  "status": "completed",
  "prompt": "A cyberpunk city with flying cars and neon signs",
  "created_at": 1704067200.123,
  "started_at": 1704067205.456,
  "completed_at": 1704067250.789,
  "progress": 100,
  "current_step": 50,
  "total_steps": 50,
  "estimated_remaining": 0,
  "error": null,
  "result": {
    "created": 1704067250,
    "data": [
      {
        "b64_json": "/9j/4AAQSkZJRg..."
      }
    ]
  }
}
```

#### Response (Failed)

```json
{
  "job_id": "a1b2c3d4",
  "status": "failed",
  "prompt": "A cyberpunk city with flying cars and neon signs",
  "created_at": 1704067200.123,
  "started_at": 1704067205.456,
  "completed_at": 1704067210.789,
  "progress": 0,
  "current_step": 0,
  "total_steps": 50,
  "estimated_remaining": null,
  "error": "CUDA out of memory"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 404 | Job not found |

---

### Cancel Job

Cancel a queued job. Only jobs with status `queued` can be cancelled.

```
DELETE /v1/jobs/{job_id}
```

#### Example Request

```bash
curl -X DELETE http://localhost:8002/v1/jobs/a1b2c3d4
```

#### Response

```json
{
  "message": "Job cancelled",
  "job_id": "a1b2c3d4"
}
```

#### Error Responses

| Status | Description |
|--------|-------------|
| 400 | Job cannot be cancelled (not queued) |
| 404 | Job not found |

---

### Get Queue Status

Get the current state of the job queue.

```
GET /v1/queue
```

#### Example Request

```bash
curl http://localhost:8002/v1/queue
```

#### Response

```json
{
  "max_queue_size": 5,
  "running": {
    "job_id": "a1b2c3d4",
    "prompt": "A cyberpunk city with flying cars...",
    "status": "running",
    "created_at": 1704067200.123,
    "progress": 45,
    "current_step": 23,
    "total_steps": 50,
    "estimated_remaining": 12.5
  },
  "queued": [
    {
      "job_id": "e5f6g7h8",
      "prompt": "A serene mountain landscape...",
      "status": "queued",
      "created_at": 1704067210.456,
      "position": 1
    }
  ],
  "recent_completed": [
    {
      "job_id": "i9j0k1l2",
      "prompt": "Abstract art with vibrant colors...",
      "status": "completed",
      "created_at": 1704067100.789,
      "completed_at": 1704067150.123
    }
  ]
}
```

---

### Get Generation Status (Legacy)

Backward-compatible endpoint for simple status polling.

```
GET /v1/status
```

#### Response (Generating)

```json
{
  "is_generating": true,
  "job_id": "a1b2c3d4",
  "prompt": "A cyberpunk city with flying cars and neon signs",
  "progress": 45,
  "current_step": 23,
  "total_steps": 50,
  "started_at": 1704067205.456,
  "estimated_remaining": 12.5,
  "queue_length": 2
}
```

#### Response (Idle)

```json
{
  "is_generating": false,
  "job_id": null,
  "prompt": null,
  "progress": 0,
  "current_step": 0,
  "total_steps": 0,
  "started_at": null,
  "estimated_remaining": null,
  "queue_length": 0
}
```

---

### List Models

List available models (OpenAI-compatible).

```
GET /v1/models
```

#### Response

```json
{
  "object": "list",
  "data": [
    {"id": "dall-e-3", "object": "model", "created": 0, "owned_by": "openai"},
    {"id": "dall-e-2", "object": "model", "created": 0, "owned_by": "openai"},
    {"id": "Qwen/Qwen-Image-2512", "object": "model", "created": 0, "owned_by": "qwen"}
  ]
}
```

---

### List Aspect Ratios

Get supported aspect ratios and size mappings.

```
GET /v1/aspect_ratios
```

#### Response

```json
{
  "aspect_ratios": {
    "1:1": [1024, 1024],
    "16:9": [1664, 928],
    "9:16": [928, 1664],
    "4:3": [1152, 864],
    "3:4": [864, 1152],
    "3:2": [1248, 832],
    "2:3": [832, 1248]
  },
  "size_map": {
    "1024x1024": "1:1",
    "1792x1024": "16:9",
    "1024x1792": "9:16"
  }
}
```

---

### Health Check

Check if the service is running.

```
GET /health
```

#### Response

```json
{
  "status": "healthy",
  "model": "Qwen/Qwen-Image-2512"
}
```

---

## WebSocket API

Connect to `/ws` for real-time queue and progress updates.

```
ws://localhost:8002/ws
```

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8002/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Update:', data);
};

// Keep-alive ping
setInterval(() => ws.send('ping'), 30000);
```

### Message Format

The server broadcasts queue status updates:

```json
{
  "type": "queue_status",
  "max_queue_size": 5,
  "running": {
    "job_id": "a1b2c3d4",
    "prompt": "A cyberpunk city...",
    "status": "running",
    "progress": 45,
    "current_step": 23,
    "total_steps": 50,
    "estimated_remaining": 12.5
  },
  "queued": [...],
  "recent_completed": [...]
}
```

### Ping/Pong

Send `ping` to receive a pong response:

```json
{"type": "pong"}
```

---

## Job Lifecycle

```
┌──────────┐     ┌─────────┐     ┌───────────┐     ┌───────────┐
│  Submit  │────▶│ Queued  │────▶│  Running  │────▶│ Completed │
└──────────┘     └─────────┘     └───────────┘     └───────────┘
                      │                                   │
                      │ Cancel                            │
                      ▼                                   ▼
                 ┌─────────┐                         ┌─────────┐
                 │ Failed  │                         │ Failed  │
                 └─────────┘                         └─────────┘
```

### Status Values

| Status | Description |
|--------|-------------|
| `queued` | Job is waiting in queue |
| `running` | Job is currently being processed |
| `completed` | Job finished successfully, result available |
| `failed` | Job failed or was cancelled |

### Result TTL

Completed job results are retained for **24 hours** before automatic cleanup.

---

## Error Handling

All errors return JSON with a `detail` field:

```json
{
  "detail": "Error message here"
}
```

### Common HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 400 | Bad request (invalid parameters) |
| 404 | Resource not found |
| 422 | Validation error |
| 503 | Service unavailable (queue full) |

---

## Rate Limiting

- Maximum queue size: 5 jobs
- Jobs exceeding the queue limit receive HTTP 503

---

## Examples

### Python

```python
import requests
import time
import base64
from PIL import Image
from io import BytesIO

# Submit job
response = requests.post(
    "http://localhost:8002/v1/images/generations",
    json={
        "prompt": "A beautiful sunset over the ocean",
        "size": "1024x1024"
    }
)
job = response.json()
job_id = job["job_id"]

# Poll for completion
while True:
    status = requests.get(f"http://localhost:8002/v1/jobs/{job_id}").json()
    print(f"Status: {status['status']}, Progress: {status['progress']}%")

    if status["status"] == "completed":
        # Decode and save image
        b64_data = status["result"]["data"][0]["b64_json"]
        image_data = base64.b64decode(b64_data)
        image = Image.open(BytesIO(image_data))
        image.save("output.png")
        print("Image saved!")
        break
    elif status["status"] == "failed":
        print(f"Failed: {status['error']}")
        break

    time.sleep(2)
```

### JavaScript

```javascript
async function generateImage(prompt) {
  // Submit job
  const submitRes = await fetch('http://localhost:8002/v1/images/generations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, size: '1024x1024' })
  });
  const { job_id } = await submitRes.json();

  // Poll for completion
  while (true) {
    const statusRes = await fetch(`http://localhost:8002/v1/jobs/${job_id}`);
    const status = await statusRes.json();

    console.log(`Status: ${status.status}, Progress: ${status.progress}%`);

    if (status.status === 'completed') {
      const imageData = status.result.data[0].b64_json;
      const img = document.createElement('img');
      img.src = `data:image/jpeg;base64,${imageData}`;
      document.body.appendChild(img);
      break;
    } else if (status.status === 'failed') {
      console.error('Failed:', status.error);
      break;
    }

    await new Promise(r => setTimeout(r, 2000));
  }
}

generateImage('A futuristic robot in a garden');
```

### WebSocket (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8002/ws');

ws.onopen = () => console.log('Connected');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.running) {
    console.log(`Running: ${data.running.prompt}`);
    console.log(`Progress: ${data.running.progress}%`);
  }

  console.log(`Queued: ${data.queued.length} jobs`);
  console.log(`Completed: ${data.recent_completed.length} recent`);
};

// Keep connection alive
setInterval(() => ws.send('ping'), 30000);
```
