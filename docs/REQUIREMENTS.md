# JARVIS Viral Reel Video Editor - Requirements Specification

**Version:** 1.0.0
**Status:** Draft
**Last Updated:** 2026-01-08

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Input Specifications](#3-input-specifications)
4. [Core Features](#4-core-features)
5. [Processing Pipeline](#5-processing-pipeline)
6. [Output Specifications](#6-output-specifications)
7. [Technical Requirements](#7-technical-requirements)
8. [User Interface](#8-user-interface)
9. [Performance Requirements](#9-performance-requirements)
10. [Future Enhancements](#10-future-enhancements)

---

## 1. Executive Summary

### 1.1 Purpose

JARVIS Viral Reel Editor is an autonomous AI system that transforms multi-camera long-form video content into viral short-form reels optimized for social media platforms (TikTok, Instagram Reels, YouTube Shorts).

### 1.2 Core Value Proposition

- **Input:** 2 camera angles + 1 audio track (podcast/interview style)
- **Output:** Multiple viral-optimized 15-90 second vertical reels
- **Automation:** AI-driven moment detection, camera switching, and editing

### 1.3 Target Use Cases

- Podcast episodes with host + guest cameras
- Interview recordings (interviewer + interviewee)
- Educational content with speaker + presentation views
- Live stream recordings with multiple angles
- Talking head content with wide + close-up shots

---

## 2. System Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                                  │
├─────────────────────────────────────────────────────────────────────┤
│  Camera 1 (MP4/MOV)  │  Camera 2 (MP4/MOV)  │  Audio Track (WAV/MP3)│
└──────────┬───────────┴──────────┬───────────┴──────────┬────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SYNC & ANALYSIS LAYER                          │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Audio Sync  │  │Transcription│  │ Speaker     │  │ Face/Person │ │
│  │ Engine      │  │ (Whisper)   │  │ Diarization │  │ Detection   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└──────────┬───────────────────────────────┬──────────────────────────┘
           │                               │
           ▼                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      INTELLIGENCE LAYER                             │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ Viral Moment    │  │ Camera Switch   │  │ Emotion/Energy      │  │
│  │ Detection (LLM) │  │ Decision Engine │  │ Analysis            │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EDITING LAYER                                  │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │ Multi-Cam   │  │ Dynamic     │  │ Subtitle    │  │ Audio       │ │
│  │ Compositor  │  │ Crop/Zoom   │  │ Generator   │  │ Enhancement │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │
└──────────┬──────────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         OUTPUT LAYER                                │
├─────────────────────────────────────────────────────────────────────┤
│  Vertical Reels (9:16)  │  Premiere Pro XML  │  Metadata/Analytics │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Core Principles

1. **Autonomous Operation** - Minimal human intervention required
2. **Quality First** - Professional broadcast-quality output
3. **Viral Optimization** - AI-driven content selection for engagement
4. **Flexibility** - Support various input configurations
5. **Speed** - GPU-accelerated processing pipeline

---

## 3. Input Specifications

### 3.1 Video Inputs

#### 3.1.1 Camera 1 (Primary/Wide Shot)

| Attribute | Requirement |
|-----------|-------------|
| **Formats** | MP4, MOV, MKV, AVI, WEBM |
| **Codecs** | H.264, H.265/HEVC, ProRes, VP9 |
| **Resolution** | 1080p minimum, 4K recommended |
| **Frame Rate** | 24, 25, 30, 60 fps |
| **Duration** | 1 minute to 4 hours |
| **Typical Use** | Wide shot, both speakers visible |

#### 3.1.2 Camera 2 (Secondary/Close-up)

| Attribute | Requirement |
|-----------|-------------|
| **Formats** | Same as Camera 1 |
| **Codecs** | Same as Camera 1 |
| **Resolution** | 1080p minimum, 4K recommended |
| **Frame Rate** | Must match Camera 1 (or auto-convert) |
| **Duration** | Must cover same time range as Camera 1 |
| **Typical Use** | Close-up of guest/secondary speaker |

#### 3.1.3 Frame Rate Handling

- If frame rates differ, system will conform to primary camera
- Frame blending or optical flow interpolation for conversion
- Warning issued if frame rate mismatch detected

### 3.2 Audio Input

#### 3.2.1 External Audio Track

| Attribute | Requirement |
|-----------|-------------|
| **Formats** | WAV, MP3, AAC, FLAC, M4A |
| **Sample Rate** | 44.1kHz or 48kHz |
| **Bit Depth** | 16-bit or 24-bit |
| **Channels** | Mono or Stereo |
| **Quality** | Clean voice, minimal background noise |

#### 3.2.2 Audio Source Priority

1. **External audio file** (highest priority - cleanest source)
2. **Camera 1 embedded audio** (fallback)
3. **Camera 2 embedded audio** (last resort)

### 3.3 Synchronization Requirements

#### 3.3.1 Sync Methods (Auto-Detected)

| Method | Description | Accuracy |
|--------|-------------|----------|
| **Audio Waveform** | Cross-correlation of audio tracks | ±1 frame |
| **Timecode** | SMPTE timecode in metadata | Exact |
| **Clap Detection** | Visual + audio spike detection | ±2 frames |
| **Manual Offset** | User-provided offset in seconds | User-defined |

#### 3.3.2 Sync Validation

- System MUST verify sync accuracy before processing
- Visual preview of sync point for user confirmation
- Auto-detect and warn of drift (>100ms over duration)

---

## 4. Core Features

### 4.1 Audio-Video Synchronization

#### 4.1.1 Automatic Sync Engine

```python
class SyncEngine:
    """
    Synchronizes multiple video files with external audio.

    Methods:
    - analyze_audio_fingerprint(): Extract audio characteristics
    - find_sync_point(): Cross-correlate to find offset
    - validate_sync(): Verify alignment accuracy
    - apply_sync(): Adjust timelines to match
    """
```

**Requirements:**

- [ ] Extract audio from all video sources
- [ ] Generate audio fingerprints/waveforms
- [ ] Cross-correlate to find optimal alignment
- [ ] Handle recordings started at different times
- [ ] Detect and compensate for audio drift
- [ ] Support manual sync point override
- [ ] Verify sync accuracy with confidence score

#### 4.1.2 Sync Output

- Unified timeline with all sources aligned
- Frame-accurate synchronization (±1 frame tolerance)
- Sync report with confidence metrics

### 4.2 GPU-Accelerated Transcription

#### 4.2.1 Whisper Integration

| Setting | Value |
|---------|-------|
| **Model** | `large-v3` (best accuracy) |
| **Compute** | CUDA GPU with float16 |
| **Output** | Word-level timestamps |
| **Languages** | Auto-detect, 99+ supported |

#### 4.2.2 Transcription Output

```json
{
  "segments": [
    {
      "start": 0.0,
      "end": 4.5,
      "text": "Welcome to the show today",
      "words": [
        {"word": "Welcome", "start": 0.0, "end": 0.4, "confidence": 0.98},
        {"word": "to", "start": 0.4, "end": 0.5, "confidence": 0.99},
        {"word": "the", "start": 0.5, "end": 0.6, "confidence": 0.97},
        {"word": "show", "start": 0.6, "end": 0.9, "confidence": 0.96},
        {"word": "today", "start": 0.9, "end": 1.3, "confidence": 0.98}
      ],
      "speaker": "SPEAKER_01"
    }
  ]
}
```

### 4.3 Speaker Diarization

#### 4.3.1 Requirements

- [ ] Identify distinct speakers in audio
- [ ] Assign speaker labels to transcript segments
- [ ] Map speakers to camera angles
- [ ] Handle overlapping speech
- [ ] Confidence scoring for speaker assignments

#### 4.3.2 Speaker-to-Camera Mapping

```python
speaker_camera_map = {
    "SPEAKER_01": {
        "name": "Host",
        "primary_camera": "camera_1",  # Wide shot when speaking
        "reaction_camera": "camera_2"  # Show guest reaction
    },
    "SPEAKER_02": {
        "name": "Guest",
        "primary_camera": "camera_2",  # Close-up when speaking
        "reaction_camera": "camera_1"  # Show host reaction
    }
}
```

### 4.4 Viral Moment Detection

#### 4.4.1 Detection Criteria

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Hook Strength** | 25% | Opening captures attention |
| **Emotional Peak** | 20% | High energy/emotion moments |
| **Quotable Content** | 20% | Shareable statements |
| **Story Arc** | 15% | Complete narrative in segment |
| **Controversy/Hot Take** | 10% | Polarizing opinions |
| **Humor** | 10% | Funny moments |

#### 4.4.2 LLM Analysis Prompt

```
Analyze this transcript and identify viral-worthy moments.

For each moment, provide:
1. Start and end timestamps
2. Viral score (1-100)
3. Category (hook, emotional, quotable, story, hot_take, humor)
4. Suggested hook/caption
5. Target platform optimization notes

Transcript:
{transcript}

Consider:
- TikTok: 15-60 seconds, strong hook in first 3 seconds
- Instagram Reels: 15-90 seconds, aesthetic appeal
- YouTube Shorts: 15-60 seconds, educational/entertaining
```

#### 4.4.3 Moment Output Structure

```python
@dataclass
class ViralMoment:
    id: str
    start_time: float
    end_time: float
    duration: float
    viral_score: int  # 1-100
    category: str
    transcript: str
    suggested_hook: str
    suggested_caption: str
    hashtags: List[str]
    platform_optimization: Dict[str, str]
    speakers_involved: List[str]
    energy_level: str  # low, medium, high, explosive
```

### 4.5 Intelligent Camera Switching

#### 4.5.1 Switch Decision Engine

**Rules-Based Switching:**

| Trigger | Action | Timing |
|---------|--------|--------|
| Speaker change | Cut to active speaker | On first word |
| Long monologue (>15s) | Cut to reaction shot | 2-4s duration |
| Emotional peak | Zoom on speaker face | Hold through peak |
| Punchline/Reveal | Wide shot for reaction | On delivery |
| Question asked | Cut to respondent | Before answer |

**AI-Enhanced Switching:**

- Analyze facial expressions for reaction timing
- Detect gestures and body language
- Identify dramatic pauses
- Find natural cut points in speech

#### 4.5.2 Switch Types

```python
class CameraSwitchType(Enum):
    HARD_CUT = "hard_cut"           # Instant switch
    DISSOLVE = "dissolve"           # Cross-fade (0.3-0.5s)
    WHIP_PAN = "whip_pan"           # Fast motion blur transition
    ZOOM_TRANSITION = "zoom_trans"  # Zoom out/in between cameras
    SPLIT_SCREEN = "split_screen"   # Both cameras momentarily
```

### 4.6 Dynamic Video Effects

#### 4.6.1 Hormozi-Style Editing

| Effect | Parameters | Application |
|--------|------------|-------------|
| **Punch Zoom** | 1.2-1.4x scale, 0.1s duration | Key words/phrases |
| **Ken Burns** | Slow drift + subtle zoom | B-roll, reactions |
| **Jump Cut** | Remove pauses >0.5s | Pacing optimization |
| **Shake** | 2-5px, 0.2s duration | Impact moments |
| **Flash Frame** | White flash, 2 frames | Transitions |

#### 4.6.2 Effect Triggers

```python
effect_triggers = {
    "punch_zoom": [
        "emphasized_word",      # Detected via audio energy
        "key_phrase",           # LLM-identified important phrase
        "speaker_name_mention", # When someone is named
        "number_statistic"      # Facts and figures
    ],
    "jump_cut": [
        "silence_gap",          # >0.5s silence
        "filler_word",          # um, uh, like, you know
        "false_start"           # Sentence restart
    ],
    "reaction_insert": [
        "joke_punchline",
        "surprising_statement",
        "question_asked"
    ]
}
```

### 4.7 Smart Framing & Cropping

#### 4.7.1 Face Detection (YOLOv8)

- Detect all faces in frame
- Track faces across frames (ID persistence)
- Identify primary subject vs secondary
- Calculate optimal crop region

#### 4.7.2 Crop Strategies

| Strategy | Use Case | Implementation |
|----------|----------|----------------|
| **Center Face** | Single speaker | Face at 1/3 from top |
| **Rule of Thirds** | Interview | Speaker on left/right third |
| **Dynamic Track** | Movement | Smooth follow with easing |
| **Two-Shot Crop** | Both visible | Fit both faces in vertical |

#### 4.7.3 Safe Zones

```
┌─────────────────────────────┐
│      Title Safe (90%)       │
│  ┌───────────────────────┐  │
│  │   Action Safe (80%)   │  │
│  │  ┌─────────────────┐  │  │
│  │  │                 │  │  │
│  │  │   Face Zone     │  │  │
│  │  │   (Center)      │  │  │
│  │  │                 │  │  │
│  │  └─────────────────┘  │  │
│  │                       │  │
│  │   ┌─────────────┐     │  │
│  │   │Caption Zone │     │  │
│  │   │(Bottom 20%) │     │  │
│  │   └─────────────┘     │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

### 4.8 Subtitle Generation

#### 4.8.1 Style Presets

| Preset | Font | Size | Color | Animation |
|--------|------|------|-------|-----------|
| **Hormozi** | Impact Bold | 72px | White + Black stroke | Word pop |
| **MrBeast** | Bebas Neue | 80px | Yellow + Red shadow | Bounce |
| **Clean** | Montserrat | 48px | White + subtle shadow | Fade |
| **Minimal** | Helvetica | 36px | White 80% opacity | None |

#### 4.8.2 Word Highlighting

```python
subtitle_config = {
    "style": "hormozi",
    "words_per_line": 3,
    "max_lines": 2,
    "highlight_mode": "word_by_word",  # or "phrase"
    "highlight_color": "#FFFF00",       # Active word
    "base_color": "#FFFFFF",            # Inactive words
    "animation": "scale_pop",           # pop, bounce, none
    "position": "bottom_center",
    "margin_bottom": 150                # pixels from bottom
}
```

### 4.9 Audio Enhancement

#### 4.9.1 Processing Chain

```
Input Audio
    │
    ▼
┌─────────────────┐
│ Noise Reduction │ (RNNoise / Spectral Gating)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Normalization   │ (LUFS -14 for social media)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Compression     │ (Voice optimized, 3:1 ratio)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ EQ Enhancement  │ (Presence boost 2-5kHz)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Limiter         │ (-1dB ceiling)
└────────┬────────┘
         │
         ▼
Output Audio
```

#### 4.9.2 Silence Handling

| Silence Duration | Action |
|------------------|--------|
| < 0.3s | Keep (natural pause) |
| 0.3s - 1.0s | Compress to 0.2s |
| 1.0s - 3.0s | Compress to 0.3s |
| > 3.0s | Cut entirely |

---

## 5. Processing Pipeline

### 5.1 Pipeline Stages

```
Stage 1: INGEST
├── Validate input files
├── Extract metadata
├── Generate proxies (if needed)
└── Estimate processing time

Stage 2: SYNCHRONIZE
├── Extract audio from all sources
├── Analyze audio fingerprints
├── Calculate sync offsets
├── Validate alignment
└── Create unified timeline

Stage 3: ANALYZE
├── Transcribe audio (Whisper)
├── Perform speaker diarization
├── Detect faces in all frames
├── Track speakers across cameras
└── Map speakers to cameras

Stage 4: DETECT MOMENTS
├── Send transcript to LLM
├── Score viral potential
├── Identify moment boundaries
├── Rank and select top moments
└── Generate hooks/captions

Stage 5: PLAN EDITS
├── Determine camera switches
├── Calculate crop regions
├── Plan effect placements
├── Generate subtitle timing
└── Create edit decision list (EDL)

Stage 6: RENDER
├── Apply crops and transforms
├── Execute camera switches
├── Render effects and transitions
├── Burn in subtitles
├── Apply audio processing
└── Encode final output

Stage 7: EXPORT
├── Generate video files
├── Create Premiere Pro XML
├── Export metadata/analytics
├── Generate thumbnails
└── Create social media copies
```

### 5.2 Pipeline Configuration

```python
pipeline_config = {
    "stages": {
        "ingest": {"enabled": True, "parallel": False},
        "sync": {"enabled": True, "parallel": False},
        "analyze": {"enabled": True, "parallel": True},
        "detect": {"enabled": True, "parallel": False},
        "plan": {"enabled": True, "parallel": False},
        "render": {"enabled": True, "parallel": True},
        "export": {"enabled": True, "parallel": True}
    },
    "checkpoints": {
        "save_after_stage": ["sync", "analyze", "detect"],
        "checkpoint_dir": "./checkpoints"
    },
    "recovery": {
        "resume_from_checkpoint": True,
        "max_retries": 3
    }
}
```

---

## 6. Output Specifications

### 6.1 Video Output

#### 6.1.1 Primary Output Format

| Attribute | Value |
|-----------|-------|
| **Resolution** | 1080x1920 (9:16 vertical) |
| **Frame Rate** | 30fps |
| **Codec** | H.264 (h264_nvenc on GPU) |
| **Bitrate** | 8-12 Mbps (VBR) |
| **Audio Codec** | AAC |
| **Audio Bitrate** | 192 kbps |
| **Container** | MP4 |

#### 6.1.2 Platform-Specific Exports

| Platform | Resolution | Duration | File Size |
|----------|------------|----------|-----------|
| **TikTok** | 1080x1920 | 15-60s | <287MB |
| **Instagram Reels** | 1080x1920 | 15-90s | <250MB |
| **YouTube Shorts** | 1080x1920 | 15-60s | <256MB |
| **Twitter/X** | 1080x1920 | 15-140s | <512MB |

### 6.2 Project Files

#### 6.2.1 Premiere Pro XML

- Full timeline with all cuts
- Linked source media
- Adjustment layers for effects
- Subtitle track (SRT import ready)
- Markers at key moments

#### 6.2.2 DaVinci Resolve (Future)

- XML or AAF export
- Color grade nodes
- Fairlight audio setup

### 6.3 Metadata Export

```json
{
  "project_id": "uuid",
  "created_at": "2026-01-08T12:00:00Z",
  "source_files": {
    "camera_1": {"path": "...", "duration": 3600},
    "camera_2": {"path": "...", "duration": 3600},
    "audio": {"path": "...", "duration": 3600}
  },
  "reels_generated": [
    {
      "id": "reel_001",
      "output_path": "output/reel_001.mp4",
      "duration": 45.2,
      "viral_score": 87,
      "category": "quotable",
      "transcript": "...",
      "suggested_caption": "...",
      "hashtags": ["#podcast", "#viral"],
      "thumbnail_path": "output/thumbs/reel_001.jpg",
      "speakers": ["Host", "Guest"],
      "camera_switches": 12,
      "effects_applied": ["punch_zoom", "jump_cut"]
    }
  ],
  "processing_stats": {
    "total_time_seconds": 1234,
    "gpu_utilization": 0.85,
    "stages_completed": ["ingest", "sync", "analyze", "detect", "plan", "render", "export"]
  }
}
```

### 6.4 Thumbnail Generation

- Auto-generate at peak engagement frame
- Face detection for optimal framing
- Multiple aspect ratios (1:1, 9:16, 16:9)
- Text overlay option with title

---

## 7. Technical Requirements

### 7.1 Hardware Requirements

#### 7.1.1 Minimum

| Component | Requirement |
|-----------|-------------|
| **CPU** | 8-core modern processor |
| **RAM** | 16GB |
| **GPU** | NVIDIA GTX 1660 (6GB VRAM) |
| **Storage** | 100GB SSD free space |

#### 7.1.2 Recommended

| Component | Requirement |
|-----------|-------------|
| **CPU** | 16-core (Ryzen 9 / i9) |
| **RAM** | 64GB |
| **GPU** | NVIDIA RTX 4080 (16GB VRAM) |
| **Storage** | 1TB NVMe SSD |

#### 7.1.3 Cloud/RunPod Configuration

| Instance Type | vCPU | RAM | GPU | Use Case |
|---------------|------|-----|-----|----------|
| **Basic** | 8 | 32GB | RTX 3080 | Short videos (<30 min) |
| **Standard** | 16 | 64GB | RTX 4080 | Medium videos (30-90 min) |
| **Pro** | 32 | 128GB | A100 40GB | Long videos (>90 min) |

### 7.2 Software Dependencies

#### 7.2.1 Core Dependencies

```txt
# AI/ML
torch>=2.0.0
faster-whisper>=1.0.0
ultralytics>=8.0.0  # YOLOv8
pyannote-audio>=3.0.0  # Speaker diarization
ollama>=0.1.0

# Video/Audio Processing
ffmpeg-python>=0.2.0
opencv-python>=4.8.0
moviepy>=1.0.3
pydub>=0.25.1
librosa>=0.10.0
numpy>=1.24.0
pillow>=10.0.0

# Configuration
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0

# CLI/UI
typer>=0.9.0
rich>=13.0.0
tqdm>=4.65.0

# Async
aiohttp>=3.9.0
aiofiles>=23.0.0

# Utilities
loguru>=0.7.0
tenacity>=8.2.0
```

#### 7.2.2 System Dependencies

```bash
# FFmpeg with NVIDIA support
ffmpeg (compiled with --enable-nvenc --enable-cuda)

# NVIDIA CUDA Toolkit
cuda-toolkit >= 11.8

# cuDNN
cudnn >= 8.6
```

### 7.3 API Integrations

#### 7.3.1 Ollama (Local LLM)

```python
ollama_config = {
    "host": "http://localhost:11434",
    "model": "llama3.1:8b",  # or "llama3.1:70b" for better quality
    "timeout": 300,
    "temperature": 0.7,
    "max_tokens": 4096
}
```

#### 7.3.2 RunPod (Cloud GPU) - Future

```python
runpod_config = {
    "api_key": "${RUNPOD_API_KEY}",
    "endpoint_id": "${RUNPOD_ENDPOINT}",
    "gpu_type": "NVIDIA RTX 4080",
    "timeout": 3600
}
```

---

## 8. User Interface

### 8.1 CLI Interface

#### 8.1.1 Primary Commands

```bash
# Process video with all defaults
jarvis process --camera1 cam1.mp4 --camera2 cam2.mp4 --audio voice.wav

# Specify output directory and reel count
jarvis process \
  --camera1 cam1.mp4 \
  --camera2 cam2.mp4 \
  --audio voice.wav \
  --output ./reels \
  --num-reels 10

# Advanced options
jarvis process \
  --camera1 cam1.mp4 \
  --camera2 cam2.mp4 \
  --audio voice.wav \
  --sync-method waveform \
  --style hormozi \
  --min-duration 30 \
  --max-duration 60 \
  --subtitle-style hormozi \
  --export-premiere \
  --gpu 0

# Analyze only (no rendering)
jarvis analyze --camera1 cam1.mp4 --audio voice.wav --output analysis.json

# Sync check
jarvis sync-check --camera1 cam1.mp4 --camera2 cam2.mp4 --audio voice.wav
```

#### 8.1.2 Configuration File

```yaml
# jarvis.yaml
input:
  camera1: ./media/camera1.mp4
  camera2: ./media/camera2.mp4
  audio: ./media/audio.wav

sync:
  method: waveform  # waveform, timecode, clap, manual
  manual_offset: 0.0

output:
  directory: ./output
  num_reels: 8
  min_duration: 30
  max_duration: 60

style:
  editing: hormozi
  subtitles: hormozi
  transitions: hard_cut

speakers:
  - name: Host
    camera: camera1
  - name: Guest
    camera: camera2

processing:
  gpu_device: 0
  whisper_model: large-v3
  llm_model: llama3.1:8b
  export_premiere: true
```

### 8.2 Python API

```python
from jarvis import ViralReelEditor

# Initialize editor
editor = ViralReelEditor(
    camera1_path="cam1.mp4",
    camera2_path="cam2.mp4",
    audio_path="voice.wav",
    output_dir="./output"
)

# Configure
editor.set_style("hormozi")
editor.set_reel_count(10)
editor.set_duration_range(30, 60)

# Map speakers to cameras
editor.map_speaker("Host", camera="camera1")
editor.map_speaker("Guest", camera="camera2")

# Process
result = editor.process()

# Access results
for reel in result.reels:
    print(f"Reel: {reel.path}")
    print(f"Score: {reel.viral_score}")
    print(f"Caption: {reel.suggested_caption}")
```

### 8.3 Progress Reporting

```
JARVIS Viral Reel Editor v1.0.0
================================

[1/7] Ingesting media files...
      ├── Camera 1: cam1.mp4 (1:32:45, 4K, 30fps) ✓
      ├── Camera 2: cam2.mp4 (1:32:45, 4K, 30fps) ✓
      └── Audio: voice.wav (1:32:45, 48kHz, stereo) ✓

[2/7] Synchronizing sources...
      ├── Analyzing audio fingerprints... ✓
      ├── Calculating sync offsets...
      │   ├── Camera 1 ↔ Audio: +0.042s offset
      │   └── Camera 2 ↔ Audio: +0.128s offset
      └── Sync confidence: 99.2% ✓

[3/7] Analyzing content...
      ├── Transcribing audio... ████████████████████ 100%
      │   └── 8,432 words transcribed
      ├── Speaker diarization... ████████████████████ 100%
      │   └── 2 speakers identified (Host, Guest)
      └── Face detection... ████████████████████ 100%
          └── 2 unique faces tracked

[4/7] Detecting viral moments...
      ├── Analyzing transcript with LLM... ████████████████████ 100%
      └── Found 23 potential viral moments

[5/7] Planning edits...
      ├── Selecting top 10 moments by viral score
      ├── Planning camera switches (avg 8.3/reel)
      └── Generating subtitle timing

[6/7] Rendering reels...
      ├── Reel 1/10: "The secret to..." ████████████████████ 100%
      ├── Reel 2/10: "Why most people..." ████████████████████ 100%
      ...
      └── Reel 10/10: "Here's what..." ████████████████████ 100%

[7/7] Exporting...
      ├── Video files: ./output/reels/ ✓
      ├── Premiere Pro XML: ./output/project.xml ✓
      ├── Thumbnails: ./output/thumbs/ ✓
      └── Metadata: ./output/metadata.json ✓

================================
Complete! 10 reels generated in 12m 34s
Top viral score: 94 (reel_003.mp4)
Output directory: ./output/
```

---

## 9. Performance Requirements

### 9.1 Processing Time Targets

| Source Duration | Target Processing Time | Ratio |
|-----------------|------------------------|-------|
| 30 minutes | < 15 minutes | 0.5x |
| 1 hour | < 25 minutes | 0.4x |
| 2 hours | < 45 minutes | 0.375x |
| 4 hours | < 90 minutes | 0.375x |

### 9.2 Quality Metrics

| Metric | Target |
|--------|--------|
| **Sync Accuracy** | ±1 frame (33ms @ 30fps) |
| **Transcription WER** | < 5% (clean audio) |
| **Face Detection** | > 95% recall |
| **Speaker ID Accuracy** | > 90% |
| **Output Bitrate** | 8-12 Mbps |

### 9.3 Resource Utilization

| Resource | Target Utilization |
|----------|-------------------|
| **GPU** | > 80% during render |
| **CPU** | > 60% during analysis |
| **RAM** | < 80% peak |
| **VRAM** | < 90% peak |

---

## 10. Future Enhancements

### 10.1 Phase 2 Features

- [ ] Web UI dashboard
- [ ] Batch processing queue
- [ ] Custom LLM fine-tuning for viral detection
- [ ] A/B thumbnail testing
- [ ] Direct social media upload API
- [ ] Real-time preview during edit planning

### 10.2 Phase 3 Features

- [ ] Multi-language support (auto-translate)
- [ ] Voice cloning for dubbing
- [ ] Custom brand templates
- [ ] Analytics dashboard (post-publish tracking)
- [ ] Collaboration features
- [ ] Mobile app companion

### 10.3 Integration Roadmap

| Integration | Priority | Status |
|-------------|----------|--------|
| RunPod Cloud GPU | High | Planned |
| Telegram Bot | Medium | Planned |
| Discord Bot | Medium | Planned |
| Zapier/n8n | Low | Future |
| Adobe Creative Cloud | Low | Future |

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Diarization** | Process of identifying "who spoke when" in audio |
| **EDL** | Edit Decision List - sequence of edit points |
| **Hormozi Style** | Fast-paced editing with zoom punches and jump cuts |
| **LUFS** | Loudness Units Full Scale - audio loudness standard |
| **Viral Score** | AI-computed engagement potential (1-100) |
| **Waveform Sync** | Alignment by matching audio wave patterns |

---

## Appendix B: Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `E001` | Input file not found | Check file path |
| `E002` | Unsupported format | Convert to supported format |
| `E003` | Sync failed | Try manual offset |
| `E004` | GPU out of memory | Reduce batch size or use smaller model |
| `E005` | LLM timeout | Check Ollama service |
| `E006` | Render failed | Check FFmpeg installation |

---

**Document End**
