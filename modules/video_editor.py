"""
Video Editor Module - Creates viral short-form content from long videos

Features:
- GPU-accelerated transcription (faster-whisper)
- AI analysis for viral moment detection (Ollama)
- Face/person tracking (YOLOv8)
- Hormozi-style editing (dynamic cuts, zooms)
- Word-synced subtitles
- Silence removal
- Audio normalization
- 9:16 vertical output
"""
import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("video_editor")


@dataclass
class Word:
    """A transcribed word with timing"""
    text: str
    start: float
    end: float
    confidence: float = 1.0


@dataclass
class Segment:
    """A segment of transcript"""
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)


@dataclass
class ViralMoment:
    """A detected viral moment"""
    start: float
    end: float
    score: float
    reason: str
    hook: str  # The opening hook/quote


@dataclass
class FaceDetection:
    """Face detection result for a frame"""
    frame_num: int
    x: int
    y: int
    width: int
    height: int
    confidence: float


class VideoEditorModule(BaseModule):
    """
    Creates viral short-form reels from long-form video content.
    """

    name = "video_editor"
    description = "Creates viral short-form content from long videos"
    version = "0.2.0"

    # Keywords that indicate video editing task
    TASK_KEYWORDS = [
        "video", "reel", "clip", "edit", "cut", "shorts", "tiktok",
        "instagram", "youtube shorts", "viral", "transcribe"
    ]

    def __init__(self):
        super().__init__()
        self.transcriber = None
        self.yolo_model = None

    def can_handle(self, task: str) -> bool:
        """Check if this is a video editing task"""
        task_lower = task.lower()
        return any(kw in task_lower for kw in self.TASK_KEYWORDS)

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate video file exists"""
        video_path = kwargs.get("video_path")
        if not video_path:
            return False, "video_path is required"

        path = Path(video_path)
        if not path.exists():
            return False, f"Video file not found: {video_path}"

        return True, None

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute video editing pipeline"""
        video_path = Path(kwargs["video_path"])
        output_dir = Path(kwargs.get("output_dir", settings.output_dir))
        num_reels = kwargs.get("num_reels", settings.target_reels)

        output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Processing video: {video_path.name}")
        self.logger.info(f"Target reels: {num_reels}")

        try:
            # Step 1: Get video info
            self.logger.info("[1/6] Analyzing video...")
            video_info = self._get_video_info(video_path)
            self.logger.info(f"Duration: {video_info['duration']:.1f}s, Resolution: {video_info['width']}x{video_info['height']}")

            # Step 2: Transcribe with word-level timestamps
            self.logger.info("[2/6] Transcribing audio (GPU)...")
            segments = self._transcribe(video_path)
            self.logger.info(f"Transcribed {len(segments)} segments")

            # Step 3: Find viral moments with AI
            self.logger.info("[3/6] Finding viral moments (AI)...")
            moments = self._find_viral_moments(segments, num_reels)
            self.logger.info(f"Found {len(moments)} viral moments")

            # Step 4: Detect faces for smart cropping
            self.logger.info("[4/6] Detecting faces for smart crop...")
            face_data = self._detect_faces(video_path, moments)

            # Step 5: Generate reels
            self.logger.info("[5/6] Generating reels...")
            reel_paths = []
            for i, moment in enumerate(moments):
                self.logger.info(f"Creating reel {i+1}/{len(moments)}: {moment.hook[:50]}...")
                reel_path = output_dir / f"reel_{i+1:02d}.mp4"
                words_for_moment = self._get_words_for_timerange(segments, moment.start, moment.end)
                self._create_reel(
                    video_path=video_path,
                    output_path=reel_path,
                    moment=moment,
                    words=words_for_moment,
                    face_data=face_data.get(i, []),
                    video_info=video_info
                )
                reel_paths.append(reel_path)

            # Step 6: Generate Premiere Pro XML (optional)
            self.logger.info("[6/6] Generating Premiere Pro XML...")
            xml_path = output_dir / "project.xml"
            self._generate_premiere_xml(video_path, moments, xml_path)

            return TaskResult(
                success=True,
                data={
                    "reels": [str(p) for p in reel_paths],
                    "xml_project": str(xml_path),
                    "moments": [
                        {"start": m.start, "end": m.end, "hook": m.hook, "score": m.score}
                        for m in moments
                    ]
                },
                metadata={"video": str(video_path), "num_reels": len(reel_paths)}
            )

        except Exception as e:
            self.logger.error(f"Video editing failed: {e}")
            import traceback
            traceback.print_exc()
            return TaskResult(success=False, error=str(e))

    def _get_video_info(self, video_path: Path) -> dict:
        """Get video metadata using ffprobe"""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0 or not result.stdout:
            raise RuntimeError(f"ffprobe failed for {video_path}: {result.stderr}")

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse ffprobe output: {e}")

        # Find video stream
        video_stream = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                video_stream = s
                break

        if not video_stream:
            raise RuntimeError(f"No video stream found in {video_path}")

        # Parse frame rate safely (avoid eval)
        fps_str = video_stream.get("r_frame_rate", "30/1")
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else 30.0
            else:
                fps = float(fps_str)
        except (ValueError, ZeroDivisionError):
            fps = 30.0

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid video dimensions: {width}x{height}")

        return {
            "duration": float(data["format"].get("duration", 0)),
            "width": width,
            "height": height,
            "fps": fps,
        }

    def _transcribe(self, video_path: Path) -> list[Segment]:
        """Transcribe video with faster-whisper (GPU accelerated)"""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper")

        if self.transcriber is None:
            self.logger.info(f"Loading Whisper model: {settings.whisper_model}")
            self.transcriber = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type
            )

        # Auto-detect language (supports Hebrew, English, etc.)
        segments_raw, info = self.transcriber.transcribe(
            str(video_path),
            word_timestamps=True,
            language=None  # Auto-detect
        )
        self.logger.info(f"Detected language: {info.language}")

        segments = []
        for seg in segments_raw:
            words = []
            if seg.words:
                for w in seg.words:
                    words.append(Word(
                        text=w.word.strip(),
                        start=w.start,
                        end=w.end,
                        confidence=w.probability
                    ))
            segments.append(Segment(
                text=seg.text.strip(),
                start=seg.start,
                end=seg.end,
                words=words
            ))

        return segments

    def _find_viral_moments(self, segments: list[Segment], num_moments: int) -> list[ViralMoment]:
        """Use Ollama LLM to find viral moments in transcript"""
        try:
            import ollama
        except ImportError:
            raise RuntimeError("ollama not installed. Run: pip install ollama")

        # Build transcript with timestamps
        transcript_text = ""
        for seg in segments:
            transcript_text += f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}\n"

        prompt = f"""You are a viral content expert. Analyze this video transcript and find the {num_moments} BEST moments for short-form viral reels (15-40 seconds each).

TRANSCRIPT:
{transcript_text}

For each moment, identify:
1. Strong hooks (questions, bold statements, surprising facts)
2. Complete thoughts/stories (don't cut mid-sentence)
3. Emotional peaks (humor, insight, controversy)
4. Actionable advice or valuable insights

Return EXACTLY {num_moments} moments as JSON array:
[
  {{
    "start": <start_seconds>,
    "end": <end_seconds>,
    "score": <1-10 viral potential>,
    "reason": "<why this will go viral>",
    "hook": "<the opening line/hook>"
  }}
]

RULES:
- Each clip must be 15-40 seconds
- Start at natural sentence beginnings
- End at natural conclusions
- No overlapping clips
- Prioritize by viral potential

Return ONLY the JSON array, no other text."""

        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response["message"]["content"]

            # Extract JSON from response
            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                moments_data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON array found in response")

            moments = []
            for m in moments_data[:num_moments]:
                moments.append(ViralMoment(
                    start=float(m["start"]),
                    end=float(m["end"]),
                    score=float(m.get("score", 5)),
                    reason=m.get("reason", ""),
                    hook=m.get("hook", "")
                ))

            # Sort by score (best first)
            moments.sort(key=lambda x: x.score, reverse=True)
            return moments

        except Exception as e:
            self.logger.warning(f"Ollama analysis failed: {e}, using fallback")
            return self._fallback_moment_detection(segments, num_moments)

    def _fallback_moment_detection(self, segments: list[Segment], num_moments: int) -> list[ViralMoment]:
        """Fallback: split video into equal parts if AI fails"""
        if not segments:
            return []

        total_duration = segments[-1].end
        target_duration = 30.0  # 30 second clips
        moments = []

        # Find natural break points (longer pauses between segments)
        current_start = 0.0
        for i, seg in enumerate(segments):
            duration = seg.end - current_start
            if duration >= settings.min_reel_duration:
                # Check if this is a good break point
                if i < len(segments) - 1:
                    gap = segments[i+1].start - seg.end
                    if gap > 0.5 or duration >= target_duration:  # Natural pause or long enough
                        moments.append(ViralMoment(
                            start=current_start,
                            end=seg.end,
                            score=5.0,
                            reason="Auto-detected segment",
                            hook=seg.text[:50] if seg.text else ""
                        ))
                        current_start = segments[i+1].start if i < len(segments) - 1 else seg.end

                        if len(moments) >= num_moments:
                            break

        return moments[:num_moments]

    def _detect_faces(self, video_path: Path, moments: list[ViralMoment]) -> dict[int, list[FaceDetection]]:
        """Detect faces in video for smart cropping using YOLOv8"""
        try:
            from ultralytics import YOLO
            import cv2
        except ImportError:
            self.logger.warning("YOLOv8 or OpenCV not available, using center crop")
            return {}

        if self.yolo_model is None:
            self.logger.info("Loading YOLOv8 model...")
            self.yolo_model = YOLO("yolov8n.pt")

        face_data = {}
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)

        for i, moment in enumerate(moments):
            detections = []
            # Sample frames throughout the moment (clamp to valid range)
            mid_time = (moment.start + moment.end) / 2
            end_sample = max(moment.start, moment.end - 0.5)  # Don't go before start
            sample_times = [
                moment.start,
                mid_time,
                end_sample
            ]

            for t in sample_times:
                frame_num = int(t * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Run YOLO detection (class 0 = person)
                results = self.yolo_model(frame, classes=[0], verbose=False)
                for r in results:
                    for box in r.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        detections.append(FaceDetection(
                            frame_num=frame_num,
                            x=x1,
                            y=y1,
                            width=x2 - x1,
                            height=y2 - y1,
                            confidence=float(box.conf)
                        ))

            face_data[i] = detections

        cap.release()
        return face_data

    def _get_words_for_timerange(self, segments: list[Segment], start: float, end: float) -> list[Word]:
        """Get all words within a time range"""
        words = []
        for seg in segments:
            if seg.end < start or seg.start > end:
                continue
            for word in seg.words:
                if start <= word.start <= end:
                    words.append(word)
        return words

    def _create_reel(
        self,
        video_path: Path,
        output_path: Path,
        moment: ViralMoment,
        words: list[Word],
        face_data: list[FaceDetection],
        video_info: dict
    ) -> None:
        """Create a single reel with all effects including hook intro"""

        # Calculate crop region (center on face or center of frame)
        src_w, src_h = video_info["width"], video_info["height"]
        target_w, target_h = settings.output_width, settings.output_height
        target_ratio = target_w / target_h  # 9:16 = 0.5625

        if face_data:
            # Filter detections by confidence (keep only strong detections)
            strong_detections = [f for f in face_data if f.confidence > 0.5]
            if not strong_detections:
                strong_detections = face_data

            # Use weighted average by confidence
            total_conf = sum(f.confidence for f in strong_detections)
            if total_conf > 0:
                avg_x = sum((f.x + f.width/2) * f.confidence for f in strong_detections) / total_conf
                avg_face_top = sum(f.y * f.confidence for f in strong_detections) / total_conf
                avg_face_height = sum(f.height * f.confidence for f in strong_detections) / total_conf
            else:
                avg_x = sum(f.x + f.width/2 for f in strong_detections) / len(strong_detections)
                avg_face_top = sum(f.y for f in strong_detections) / len(strong_detections)
                avg_face_height = sum(f.height for f in strong_detections) / len(strong_detections)

            # Head is at top 15-25% of person bounding box (YOLO detects full body)
            head_y = avg_face_top + avg_face_height * 0.2
            center_x = int(avg_x)

            # Safety: ensure center_x is not too close to edges
            min_margin = src_w * 0.15  # 15% margin from edges
            center_x = max(min_margin, min(center_x, src_w - min_margin))

            self.logger.debug(f"Face detection: center_x={center_x}, head_y={head_y}, detections={len(strong_detections)}")
        else:
            # No detection - use center of frame
            center_x = src_w // 2
            head_y = src_h // 3  # Default to upper third
            self.logger.debug("No face detected, using center crop")

        # Calculate crop dimensions to get 9:16
        if src_w / src_h > target_ratio:
            # Video is wider - crop width
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            # Video is taller - crop height
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)

        # Position crop so head is at upper 1/3 of output frame
        # Upper 1/3 line is at crop_h / 3 from top
        # We want head_y (in source) to appear at crop_h/3 (in crop)
        # So: crop_y + crop_h/3 = head_y  =>  crop_y = head_y - crop_h/3
        desired_crop_y = int(head_y - crop_h / 3)
        crop_y = max(0, min(desired_crop_y, src_h - crop_h))

        # Center horizontally on subject with safety check
        desired_crop_x = int(center_x - crop_w // 2)
        crop_x = max(0, min(desired_crop_x, src_w - crop_w))

        # Safety check: if crop would cut off too much, fall back to center
        # This helps when person is at edge of frame
        if face_data:
            # Check if the detected person center is within the crop
            person_in_crop = (crop_x < center_x < crop_x + crop_w)
            if not person_in_crop:
                self.logger.warning(f"Person may be cut off, centering crop")
                crop_x = max(0, min(src_w // 2 - crop_w // 2, src_w - crop_w))

        # Create subtitle filter
        subtitle_filter = self._create_subtitle_filter(words, moment.start)

        # Build FFmpeg filter complex for Hormozi-style editing with hook
        filter_complex = self._build_filter_complex(
            crop_x, crop_y, crop_w, crop_h,
            target_w, target_h,
            moment.end - moment.start,
            subtitle_filter,
            hook_text=moment.hook  # Show hook at start of reel
        )

        # Build FFmpeg command with GPU encoding
        # Social media requirements: yuv420p + bt709 color space
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(moment.start),
            "-i", str(video_path),
            "-t", str(moment.end - moment.start),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", settings.video_codec,
            "-preset", settings.ffmpeg_preset,
            "-crf", str(settings.ffmpeg_crf),
            "-pix_fmt", "yuv420p",  # Required for social platforms
            "-colorspace", "bt709",  # SDR color space
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-c:a", settings.audio_codec,
            "-b:a", settings.audio_bitrate,
            "-movflags", "+faststart",
            str(output_path)
        ]

        self.logger.debug(f"Running FFmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Try with CPU encoding as fallback
            self.logger.warning(f"GPU encoding failed: {result.stderr[:200] if result.stderr else 'No error'}, trying CPU...")
            # Rebuild command for CPU encoding with social media requirements
            cmd_cpu = [
                "ffmpeg", "-y",
                "-ss", str(moment.start),
                "-i", str(video_path),
                "-t", str(moment.end - moment.start),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", "libx264",
                "-preset", "fast",  # Faster than medium, good quality
                "-crf", "18",  # Higher quality for social (was 23)
                "-pix_fmt", "yuv420p",  # Required for social platforms
                "-colorspace", "bt709",  # SDR color space
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
                "-c:a", settings.audio_codec,
                "-b:a", settings.audio_bitrate,
                "-movflags", "+faststart",
                str(output_path)
            ]
            result = subprocess.run(cmd_cpu, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    def _find_font(self) -> str:
        """Find an available font file for subtitles"""
        import platform
        system = platform.system()

        if system == "Windows":
            # Windows font paths (check actual paths, return FFmpeg-escaped)
            win_fonts = [
                "C:/Windows/Fonts/arialbd.ttf",   # Arial Bold
                "C:/Windows/Fonts/arial.ttf",     # Arial
                "C:/Windows/Fonts/calibrib.ttf",  # Calibri Bold
                "C:/Windows/Fonts/segoeui.ttf",   # Segoe UI
            ]
            for font in win_fonts:
                if Path(font).exists():
                    # Escape colon for FFmpeg drawtext filter
                    return font.replace(":", "\\:")
        else:
            # Linux/macOS font paths
            unix_fonts = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Helvetica.ttc",  # macOS
                "/Library/Fonts/Arial Bold.ttf",  # macOS
            ]
            for font in unix_fonts:
                if Path(font).exists():
                    return font

        # Fallback: let FFmpeg try to find a font
        self.logger.warning("No font file found, FFmpeg will use default")
        return ""

    def _clean_subtitle_text(self, text: str) -> str:
        """Remove punctuation and clean text for subtitles"""
        # Remove common punctuation
        punctuation = ".,;:!?'\"-/\\[](){}…"
        for char in punctuation:
            text = text.replace(char, "")
        # Convert to uppercase for impact
        text = text.upper().strip()
        # Remove extra spaces
        text = " ".join(text.split())

        # Add letter spacing (thin spaces between characters)
        letter_spacing = getattr(settings, 'subtitle_letter_spacing', 0)
        if letter_spacing > 0 and text:
            # Insert thin spaces between each character (except spaces)
            spaced_chars = []
            for i, char in enumerate(text):
                spaced_chars.append(char)
                # Add thin space after each char except last and before spaces
                if i < len(text) - 1 and char != ' ' and text[i+1] != ' ':
                    spaced_chars.append(' ' * letter_spacing)
            text = ''.join(spaced_chars)

        return text

    def _create_subtitle_filter(self, words: list[Word], offset: float) -> str:
        """Create drawtext filter for word-synced subtitles - bold, no punctuation, bottom 1/3"""
        if not words:
            return ""

        filters = []
        chunk_size = settings.subtitle_words_per_chunk
        font_path = self._find_font()

        # Bolder settings
        font_size = settings.subtitle_font_size + 10  # Bigger
        stroke_width = settings.subtitle_stroke_width + 2  # Bolder outline

        for i in range(0, len(words), chunk_size):
            chunk = words[i:i+chunk_size]
            text = " ".join(w.text for w in chunk)

            # Clean text: remove punctuation, uppercase
            text = self._clean_subtitle_text(text)
            if not text:
                continue

            # Escape special characters for FFmpeg drawtext (after cleaning)
            text = text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")

            # Apply subtitle timing offset (negative = show earlier for lip sync)
            sub_offset = getattr(settings, 'subtitle_offset', 0)
            start = chunk[0].start - offset + sub_offset
            end = chunk[-1].end - offset + sub_offset
            # Ensure start isn't negative
            start = max(0, start)

            # Use fontfile if found, otherwise use font name as fallback
            if font_path:
                font_clause = f"fontfile='{font_path}':"
            else:
                font_clause = f"font='{settings.subtitle_font}':"

            # Use subtitle_position_y from settings (default 0.82 = bottom 1/3)
            pos_y = getattr(settings, 'subtitle_position_y', 0.82)
            filters.append(
                f"drawtext=text='{text}':"
                f"{font_clause}"
                f"fontsize={font_size}:"
                f"fontcolor={settings.subtitle_color}:"
                f"bordercolor={settings.subtitle_stroke_color}:"
                f"borderw={stroke_width}:"
                f"x=(w-text_w)/2:y=h*{pos_y}:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )

        return ",".join(filters)

    def _build_filter_complex(
        self,
        crop_x: int, crop_y: int, crop_w: int, crop_h: int,
        target_w: int, target_h: int,
        duration: float,
        subtitle_filter: str,
        hook_text: str = ""
    ) -> str:
        """Build FFmpeg filter complex with Hormozi-style cuts and hook intro"""

        # Build video filter chain
        # 1. Crop -> 2. Scale -> 3. Color punch -> 4. Subtitles -> 5. Hook
        video_filters = [
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            f"scale={target_w}:{target_h}:flags=lanczos",
            f"fps={settings.fps}",
            # Ad punch: slight contrast + saturation boost for visual pop
            "eq=contrast=1.08:saturation=1.10",
            # Subtle sharpening for crisp text/faces
            "unsharp=5:5:0.8:5:5:0.4"
        ]

        # Add subtitles if available
        if subtitle_filter:
            video_filters.append(subtitle_filter)

        # Add hook text overlay at the beginning (first 2.5 seconds)
        if hook_text and hook_text.strip():
            hook_clean = self._clean_subtitle_text(hook_text)
            if not hook_clean:
                hook_clean = "WATCH THIS"  # Fallback hook
            if len(hook_clean) > 50:
                hook_clean = hook_clean[:50]  # Truncate long hooks
            hook_escaped = hook_clean.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")

            font_path = self._find_font()
            if font_path:
                font_clause = f"fontfile='{font_path}':"
            else:
                font_clause = f"font='{settings.subtitle_font}':"

            # Hook displayed prominently in center for first 2.5s
            video_filters.append(
                f"drawtext=text='{hook_escaped}':"
                f"{font_clause}"
                f"fontsize=80:"
                f"fontcolor=yellow:"
                f"bordercolor=black:"
                f"borderw=4:"
                f"x=(w-text_w)/2:y=h*0.4:"
                f"enable='between(t,0,2.5)'"
            )

        video_chain = ",".join(video_filters) + "[outv]"

        # Audio processing: silence removal + loudness normalization
        # 1. Remove silences > 300ms (retention booster)
        # 2. Normalize to -16 LUFS (streaming standard)
        audio_filters = [
            "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.3:stop_periods=-1:stop_threshold=-40dB:stop_silence=0.3",
            "loudnorm=I=-16:TP=-1.5:LRA=11"  # Broadcast standard normalization
        ]
        audio_chain = ",".join(audio_filters) + "[outa]"

        return f"[0:v]{video_chain};[0:a]{audio_chain}"

    def _generate_premiere_xml(self, video_path: Path, moments: list[ViralMoment], output_path: Path) -> None:
        """Generate Premiere Pro XML project file"""
        # Simplified FCP XML format
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="5">
  <project>
    <name>JARVIS Reels</name>
    <children>
      <sequence>
        <name>Reels Sequence</name>
        <media>
          <video>
            <track>
'''
        # Convert path to URL-safe format (forward slashes, proper encoding)
        video_url = str(video_path.absolute()).replace("\\", "/")

        for i, moment in enumerate(moments):
            xml_content += f'''              <clipitem id="clip{i+1}">
                <name>Reel {i+1}</name>
                <start>{int(moment.start * 30)}</start>
                <end>{int(moment.end * 30)}</end>
                <in>{int(moment.start * 30)}</in>
                <out>{int(moment.end * 30)}</out>
                <file>
                  <pathurl>file:///{video_url}</pathurl>
                </file>
              </clipitem>
'''
        xml_content += '''            </track>
          </video>
        </media>
      </sequence>
    </children>
  </project>
</xmeml>'''

        output_path.write_text(xml_content)
        self.logger.info(f"Premiere XML saved: {output_path}")
