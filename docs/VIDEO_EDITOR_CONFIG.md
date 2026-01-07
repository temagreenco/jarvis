# JARVIS Video Editor - Configuration & Progress

## Current Settings (as of 2026-01-07)

### Subtitle Settings
| Setting | Value | Notes |
|---------|-------|-------|
| `subtitle_words_per_chunk` | 4 | 2-4 words per row |
| `subtitle_font_size` | 75 | Increased 25% from 60 |
| `subtitle_font` | Arial-Bold | Bold for impact |
| `subtitle_color` | white | Main text color |
| `subtitle_stroke_color` | black | Outline color |
| `subtitle_stroke_width` | 3 | Outline thickness |
| `subtitle_position_y` | 0.65 | 65% down (safe zone) |
| `subtitle_offset` | -0.50 | Show 500ms earlier (lip sync) |
| `subtitle_duration_buffer` | 0.3 | Extend display 300ms |
| `subtitle_letter_spacing` | 0 | Disabled |
| `subtitle_uppercase` | True | ALL CAPS for impact |

### Video Output Settings
| Setting | Value | Notes |
|---------|-------|-------|
| `output_width` | 1080 | 9:16 vertical |
| `output_height` | 1920 | TikTok/Reels format |
| `fps` | 30 | Standard social media |
| `target_reels` | 8 | Reels per video |
| `min_reel_duration` | 15.0 | Seconds |
| `max_reel_duration` | 40.0 | Seconds |

### Encoding Settings (Social Media Optimized)
| Setting | Value | Notes |
|---------|-------|-------|
| `video_codec` | h264_nvenc | GPU encoding (libx264 fallback) |
| `ffmpeg_preset` | p4 | NVENC quality preset |
| `ffmpeg_crf` | 18 | High quality (was 23) |
| `audio_codec` | aac | Standard |
| `audio_bitrate` | 192k | Good quality |
| Pixel format | yuv420p | Required for social platforms |
| Color space | bt709 | SDR standard |

### Visual Enhancements
- Contrast boost: 1.08
- Saturation boost: 1.10
- Sharpening: unsharp 5:5:0.8:5:5:0.4

---

## Issues Fixed

### 1. Audio/Subtitle Sync Drift
**Problem:** Subtitles appeared after speech, sync got worse over time.
**Cause:** `silenceremove` filter changed audio duration but subtitle timings stayed fixed.
**Solution:** Disabled silenceremove, kept only loudnorm. Added `subtitle_offset = -0.50`.

### 2. Object Out of Frame (reels 01, 02, 06)
**Problem:** Person was cut off in vertical crop.
**Cause:** YOLO detected full body, not face. Head position estimate was wrong.
**Solution:** Switched to OpenCV Haar cascade for actual face detection, YOLO as fallback with face estimated as top 25% of body.

### 3. Face Not at Upper 1/3 Grid
**Problem:** Face wasn't positioned at rule-of-thirds line.
**Solution:** Changed crop calculation: `crop_y = face_target_y - crop_h/3`

### 4. Subtitle Disappeared Too Early (reel_07)
**Problem:** Subtitle vanished while speaker still saying "למרות שאני".
**Solution:** Added `subtitle_duration_buffer = 0.3` to extend display time.

### 5. Hebrew Language Support
**Problem:** Subtitles based on English transcription.
**Solution:** Set `language=None` in Whisper for auto-detection.

### 6. Safe Zone for TikTok/Reels UI
**Problem:** Subtitles overlapped with platform UI elements.
**Solution:** Adjusted `subtitle_position_y` to 0.65 (moved into safe zone).

---

## Face Detection Pipeline

1. **Primary:** OpenCV Haar cascade (`haarcascade_frontalface_default.xml`)
   - Detects actual faces
   - Confidence: 0.9
   - Parameters: scaleFactor=1.1, minNeighbors=5, minSize=50x50

2. **Fallback:** YOLOv8 person detection
   - When no faces found
   - Estimates face as top 25% of person box
   - Confidence: box.conf * 0.7 (lower due to estimation)

---

## FFmpeg Filter Chain

```
[0:v] crop -> scale -> fps -> eq(contrast/saturation) -> unsharp -> subtitles -> hook [outv]
[0:a] loudnorm [outa]
```

---

## Usage

```bash
# Process a video
python -m jarvis video process videos/input.mp4

# Automated test loop
./scripts/auto_test_video.sh videos/test.mp4
```

---

## Commit History

- `49b7205` - fix: Improve subtitle timing and increase words per chunk
- `09a88fe` - fix: Disable silenceremove to fix subtitle sync drift
- `a0b0f48` - fix: Proper face detection and centering
- `ba1db26` - fix: Crop positioning + subtitle adjustments
- `44e8fc6` - fix: Subtitle adjustments - position, spacing, sync
- `f84b20b` - fix: Hebrew support, subtitle timing and position
