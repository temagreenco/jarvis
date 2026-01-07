#!/bin/bash
# RunPod Setup Script - Fast Podcast Video Editing
# Run this after SSH into your RunPod instance

set -e

echo "=== JARVIS RunPod Setup ==="

# 1. System packages
apt-get update && apt-get install -y ffmpeg git

# 2. Clone/update repo
if [ -d "/workspace/jarvis" ]; then
    cd /workspace/jarvis && git pull
else
    git clone https://github.com/temagreenco/jarvis.git /workspace/jarvis
fi
cd /workspace/jarvis

# 3. Python dependencies (GPU optimized)
pip install --upgrade pip
pip install \
    faster-whisper \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 \
    ultralytics \
    opencv-python-headless \
    pydantic-settings \
    httpx \
    ctranslate2

# 4. Download Whisper model (cache for speed)
python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cuda', compute_type='float16')"

# 5. Download YOLO model
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# 6. Create directories
mkdir -p /workspace/jarvis/videos /workspace/jarvis/output

echo ""
echo "=== Setup Complete ==="
echo "Upload videos to: /workspace/jarvis/videos/"
echo "Run: python -m jarvis video process videos/your_video.mp4"
echo ""
