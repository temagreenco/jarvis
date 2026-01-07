"""
JARVIS Configuration - All settings in one place
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for JARVIS"""

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    videos_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "videos")
    output_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "output")
    models_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "models")

    # GPU Settings
    use_gpu: bool = True
    gpu_device: int = 0

    # Ollama Settings
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Whisper Settings
    whisper_model: str = "large-v3"  # Options: tiny, base, small, medium, large-v2, large-v3
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"  # float16 for GPU, int8 for CPU

    # YOLO Settings
    yolo_model: str = "yolov8n.pt"  # nano model, fast
    yolo_confidence: float = 0.5

    # Video Editor Settings
    target_reels: int = 8
    min_reel_duration: float = 15.0  # seconds
    max_reel_duration: float = 40.0  # seconds
    output_width: int = 1080
    output_height: int = 1920  # 9:16 vertical
    fps: int = 30

    # Subtitle Settings
    subtitle_words_per_chunk: int = 2
    subtitle_font_size: int = 60
    subtitle_font: str = "Arial-Bold"
    subtitle_color: str = "white"
    subtitle_highlight_color: str = "#FFFF00"  # Yellow highlight for current word
    subtitle_stroke_color: str = "black"
    subtitle_stroke_width: int = 3
    subtitle_shadow: bool = True
    subtitle_shadow_color: str = "#000000"
    subtitle_shadow_offset: int = 4
    subtitle_position_y: float = 0.82  # Vertical position (0-1)
    subtitle_uppercase: bool = True
    subtitle_animation: str = "pop"  # pop, fade, none

    # Editing Style (Hormozi style)
    cut_interval_min: float = 2.5  # seconds
    cut_interval_max: float = 5.0  # seconds
    zoom_enabled: bool = True
    zoom_factor: float = 1.25  # 25% zoom on cuts
    zoom_duration: float = 0.15  # seconds
    silence_threshold: float = -40  # dB
    silence_min_duration: float = 0.3  # seconds

    # Smart Tracking Settings
    dead_zone_pixels: int = 80
    smoothing_factor: float = 0.15
    momentum_decay: float = 0.85

    # Audio Settings
    loudness_target: float = -14.0  # LUFS

    # FFmpeg Settings
    ffmpeg_preset: str = "p4"  # NVENC preset: p1(fastest) to p7(quality)
    ffmpeg_crf: int = 18  # Higher quality for social media (18 = good, 23 = standard)
    crf: int = 20  # Alias for preset system
    preset: str = "medium"  # libx264 preset
    video_codec: str = "h264_nvenc"  # GPU encoding
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"

    # Chat Module Settings
    chat_temperature: float = 0.7  # Response creativity (0.0-1.0)
    chat_context_messages: int = 20  # Max messages to include for context
    chat_system_prompt: Optional[str] = None  # Custom system prompt override

    # Telegram Bot
    telegram_token: Optional[str] = None
    telegram_bot_token: Optional[str] = None  # Alternative name
    telegram_allowed_users: list[int] = Field(default_factory=list)

    # API Settings
    api_key: Optional[str] = None
    require_auth: bool = False
    bind_localhost: bool = True

    class Config:
        env_file = ".env"
        env_prefix = "JARVIS_"
        extra = "ignore"  # Ignore unknown env vars


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance"""
    return settings
