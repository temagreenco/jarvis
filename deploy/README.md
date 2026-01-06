# JARVIS Cloud Deployment

## RunPod Serverless (Recommended)

**Cost**: ~$0.00035/sec (~$1.26/hr) on RTX 4090
**Cold Start**: ~30-60 sec (models pre-loaded)
**Processing**: 10min video → ~2-3 min

### Quick Deploy

```bash
# 1. Build image
docker build -f deploy/Dockerfile.runpod -t your-registry/jarvis-gpu:latest .

# 2. Push to Docker Hub or RunPod registry
docker push your-registry/jarvis-gpu:latest

# 3. Create endpoint on runpod.io
#    - Go to Serverless → New Endpoint
#    - Select your image
#    - GPU: RTX 4090 (24GB) or A100
#    - Min Workers: 0 (scale to zero)
#    - Max Workers: 5 (adjust based on load)
```

### API Usage

```python
import httpx

RUNPOD_API_KEY = "your-api-key"
ENDPOINT_ID = "your-endpoint-id"

response = httpx.post(
    f"https://api.runpod.ai/v2/{ENDPOINT_ID}/runsync",
    headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
    json={
        "input": {
            "video_url": "https://example.com/video.mp4",
            "num_reels": 5,
            "language": "he",
            "shakshuka": False
        }
    },
    timeout=600  # 10 min timeout
)

result = response.json()
print(result["output"]["reels"])
```

### Async Processing (Long Videos)

```python
# Start job
job = httpx.post(
    f"https://api.runpod.ai/v2/{ENDPOINT_ID}/run",
    headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
    json={"input": {"video_url": "https://..."}}
).json()

job_id = job["id"]

# Poll for status
while True:
    status = httpx.get(
        f"https://api.runpod.ai/v2/{ENDPOINT_ID}/status/{job_id}",
        headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"}
    ).json()

    if status["status"] == "COMPLETED":
        print(status["output"])
        break
    elif status["status"] == "FAILED":
        print(status["error"])
        break

    time.sleep(5)
```

### Webhook (Fire & Forget)

```python
httpx.post(
    f"https://api.runpod.ai/v2/{ENDPOINT_ID}/run",
    headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
    json={
        "input": {
            "video_url": "https://...",
            "webhook_url": "https://your-server.com/webhook"
        }
    }
)
# Results sent to webhook when done
```

## Performance Comparison

| Setup | 10min Video | 30min Video | Cost |
|-------|-------------|-------------|------|
| Local (no GPU) | ~45 min | ~2+ hrs | Free |
| Local (RTX 3060) | ~15 min | ~45 min | Free |
| RunPod RTX 4090 | ~2 min | ~6 min | ~$0.02 |
| RunPod A100 | ~1.5 min | ~4 min | ~$0.05 |

## Environment Variables

```bash
# RunPod secrets (set in dashboard)
JARVIS_API_KEY=your-api-key  # For webhook auth
JARVIS_WHISPER_MODEL=large-v3
JARVIS_OLLAMA_MODEL=llama3.1:8b
```

## Storage Options

1. **Base64 in response** - Files < 10MB returned directly
2. **RunPod Network Volume** - Persistent storage, mount at /runpod-volume
3. **S3/R2** - Add boto3, upload to your bucket
4. **Webhook** - Send download URLs to your server

## Troubleshooting

**Out of memory**: Reduce `num_reels` or use A100 (80GB)
**Slow cold start**: Models pre-cached, first request ~60s
**Timeout**: Use async `/run` endpoint for videos > 20min
