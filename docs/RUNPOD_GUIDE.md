# RunPod Quick Start - Podcast Video Editing

## Recommended Pod Specs

| Type | GPU | VRAM | Speed | Cost |
|------|-----|------|-------|------|
| **Budget** | RTX 3090 | 24GB | ~3min/video | ~$0.40/hr |
| **Fast** | RTX 4090 | 24GB | ~1.5min/video | ~$0.70/hr |
| **Batch** | A100 80GB | 80GB | ~1min/video | ~$1.50/hr |

## Quick Start

### 1. Create Pod
- Template: `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel`
- Volume: 50GB+ (for models + videos)
- GPU: RTX 3090 or better

### 2. SSH & Setup
```bash
# SSH into pod
ssh root@<pod-ip>

# One-time setup
curl -sSL https://raw.githubusercontent.com/temagreenco/jarvis/main/scripts/runpod_setup.sh | bash
```

### 3. Upload Videos
```bash
# From your local machine
scp video.mp4 root@<pod-ip>:/workspace/jarvis/videos/

# Or use RunPod file browser
```

### 4. Process
```bash
cd /workspace/jarvis

# Single video
python -m jarvis video process videos/podcast.mp4

# Batch processing
python scripts/batch_process.py videos/ --output output/
```

### 5. Download Results
```bash
# From your local machine
scp -r root@<pod-ip>:/workspace/jarvis/output/ ./results/
```

## Speed Benchmarks

| Video Length | RTX 3090 | RTX 4090 | A100 |
|--------------|----------|----------|------|
| 10 min | ~2 min | ~1 min | ~45s |
| 30 min | ~5 min | ~2.5 min | ~1.5 min |
| 60 min | ~10 min | ~5 min | ~3 min |

*Processing 8 reels per video*

## Tips for Speed

1. **Use float16** - Already set in config
2. **GPU encoding** - h264_nvenc is enabled
3. **Batch at night** - Cheaper spot instances
4. **Pre-download models** - Setup script does this

## Environment Variables

Copy `config/runpod.env` to `.env`:
```bash
cp config/runpod.env .env
```

Or set directly:
```bash
export JARVIS_WHISPER_MODEL=large-v3
export JARVIS_VIDEO_CODEC=h264_nvenc
```

## Troubleshooting

### CUDA out of memory
- Reduce whisper model: `JARVIS_WHISPER_MODEL=medium`
- Process one video at a time

### Slow encoding
- Check GPU usage: `nvidia-smi`
- Ensure h264_nvenc is working, not falling back to CPU

### Model download slow
- Models cache in `/root/.cache/`
- Pre-download with setup script
