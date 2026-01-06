"""
RunPod Serverless Handler for JARVIS Video Editor

Deploy to RunPod:
1. Build: docker build -f deploy/Dockerfile.runpod -t jarvis-gpu .
2. Push: docker push your-registry/jarvis-gpu:latest
3. Create serverless endpoint on runpod.io

Usage:
    POST to endpoint with:
    {
        "input": {
            "video_url": "https://...",  # URL to video file
            "num_reels": 5,
            "language": "he",  # or "auto"
            "shakshuka": false,
            "webhook_url": "https://..."  # Optional: receive results
        }
    }
"""
import os
import sys
import tempfile
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import runpod
import httpx

# Add parent directory to path for imports
sys.path.insert(0, "/app")

from modules.video_editor import VideoEditorModule
from utils.logger import get_logger

logger = get_logger("runpod_handler")

# Pre-load models at cold start for faster inference
video_editor = None


def download_video(url: str, output_dir: Path) -> Path:
    """Download video from URL to local file."""
    parsed = urlparse(url)
    filename = Path(parsed.path).name or "input_video.mp4"
    output_path = output_dir / filename

    logger.info(f"Downloading video from {url}")

    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)

    logger.info(f"Downloaded to {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return output_path


def upload_to_storage(file_path: Path, upload_url: str = None) -> str:
    """Upload file to cloud storage and return URL.

    If no upload_url provided, uses RunPod's built-in storage.
    """
    if upload_url:
        # Upload to custom endpoint
        with open(file_path, "rb") as f:
            response = httpx.put(upload_url, content=f.read(), timeout=300)
            response.raise_for_status()
        return upload_url

    # Return base64 for small files, path for large
    file_size = file_path.stat().st_size
    if file_size < 10 * 1024 * 1024:  # < 10MB
        import base64
        with open(file_path, "rb") as f:
            return f"data:video/mp4;base64,{base64.b64encode(f.read()).decode()}"

    # For larger files, return local path (RunPod will handle)
    return str(file_path)


def handler(event: dict[str, Any]) -> dict[str, Any]:
    """RunPod serverless handler function.

    Args:
        event: RunPod event with "input" containing:
            - video_url: URL to source video
            - num_reels: Number of reels to generate (default: 5)
            - language: Language code or "auto" (default: "auto")
            - shakshuka: Enable Shakshuka mode (default: False)
            - webhook_url: Optional webhook for results

    Returns:
        Dict with generated reel URLs/paths and metadata.
    """
    global video_editor

    try:
        job_input = event.get("input", {})

        # Validate required fields
        video_url = job_input.get("video_url")
        if not video_url:
            return {"error": "video_url is required"}

        # Parse options
        num_reels = job_input.get("num_reels", 5)
        language = job_input.get("language", "auto")
        shakshuka = job_input.get("shakshuka", False)
        webhook_url = job_input.get("webhook_url")

        # Initialize video editor (cached after first call)
        if video_editor is None:
            logger.info("Initializing VideoEditorModule...")
            video_editor = VideoEditorModule()

        # Create temp directories
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            input_dir = tmpdir / "input"
            output_dir = tmpdir / "output"
            input_dir.mkdir()
            output_dir.mkdir()

            # Download video
            video_path = download_video(video_url, input_dir)

            # Process video
            logger.info(f"Processing video: reels={num_reels}, lang={language}, shakshuka={shakshuka}")

            result = video_editor.execute(
                task="Create viral reels",
                video_path=str(video_path),
                output_dir=str(output_dir),
                num_reels=num_reels,
                language=language if language != "auto" else None,
                shakshuka=shakshuka
            )

            if not result.success:
                return {"error": result.error}

            # Upload generated reels
            reel_urls = []
            for reel_path in result.data.get("reels", []):
                reel_path = Path(reel_path)
                if reel_path.exists():
                    url = upload_to_storage(reel_path)
                    reel_urls.append({
                        "name": reel_path.name,
                        "url": url,
                        "size_mb": reel_path.stat().st_size / 1024 / 1024
                    })

            response = {
                "success": True,
                "reels": reel_urls,
                "moments": result.data.get("moments", []),
                "processing_time": result.duration
            }

            # Send webhook if provided
            if webhook_url:
                try:
                    httpx.post(webhook_url, json=response, timeout=30)
                except Exception as e:
                    logger.warning(f"Webhook failed: {e}")

            return response

    except Exception as e:
        logger.error(f"Handler error: {e}")
        import traceback
        return {
            "error": str(e),
            "traceback": traceback.format_exc()
        }


# RunPod entry point
runpod.serverless.start({"handler": handler})
