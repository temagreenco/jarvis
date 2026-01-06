# JARVIS - AI Video Editor

## Environment
- **OS**: Windows 11
- **Python**: 3.11
- **FFmpeg**: 8.0.1 (with NVENC GPU encoding)
- **GPU**: NVIDIA (CUDA enabled)
- **Language**: Hebrew (RTL) support required

## Project Structure
```
F:\dev\jarvis\
├── cli.py                 # CLI entry point
├── core/
│   ├── jarvis.py          # Main orchestrator
│   ├── task_router.py     # Routes tasks to modules
│   └── memory.py          # Task history/learning
├── modules/
│   ├── base_module.py     # Abstract base class
│   └── video_editor.py    # Main video processing (600+ lines)
├── config/
│   └── settings.py        # All settings (Pydantic)
└── utils/
    └── logger.py          # Loguru logging
```

## What It Does
Creates viral short-form reels (15-40s) from long videos:
1. Transcribe with faster-whisper (GPU)
2. Find viral moments with Ollama LLM
3. Detect faces with YOLOv8 for smart cropping
4. Render 9:16 vertical reels with subtitles
5. Export Premiere Pro XML

## Key Commands
```powershell
# Standard processing
python cli.py process --video "path.mp4" --reels 5 --lang he

# With output dir
python cli.py process --video "path.mp4" --reels 5 --lang he --output ".\output\name"
```

## Settings Override (env vars)
```
JARVIS_ZOOM_ENABLED=false      # Disable zoom if FFmpeg fails
JARVIS_WHISPER_MODEL=medium    # Faster transcription
JARVIS_VIDEO_CODEC=libx264     # Force CPU encoding
```

## Known Issues & Fixes
| Issue | Solution |
|-------|----------|
| FFmpeg font not found | Uses platform-specific paths (Windows/Linux/Mac) |
| Hebrew subtitle crash | Escape special chars in `_escape_ffmpeg_text()` |
| zoompan filter fails | Replaced with scale-based zoom in v0.2.0 |
| GPU encoding fails | Auto-fallback to libx264 CPU |

## Code Style
- Type hints everywhere
- Dataclasses for data structures
- Pydantic for settings
- Loguru for logging
- subprocess for FFmpeg (not ffmpeg-python library)

## When Editing This Project
1. Test on Windows (primary platform)
2. Hebrew text must work in subtitles
3. FFmpeg filters must be cross-platform
4. Always add fallbacks for GPU features
5. Keep settings in `config/settings.py`, not hardcoded
