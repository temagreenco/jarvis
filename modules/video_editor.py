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
from typing import Optional, TypedDict
import re


class VideoInfo(TypedDict):
    """Video metadata returned from ffprobe analysis."""
    duration: float
    width: int
    height: int
    fps: float

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

    This module implements an automated pipeline for transforming long-form videos
    into engaging, viral-ready short-form content (TikTok, Instagram Reels, YouTube Shorts).

    Features:
        - **GPU-accelerated transcription**: Uses faster-whisper with CUDA support
          for real-time audio transcription with word-level timestamps.
        - **AI-powered viral moment detection**: Leverages Ollama LLMs to analyze
          transcripts and identify high-engagement segments.
        - **Smart face tracking**: YOLOv8 person detection for intelligent 9:16 cropping.
        - **Hormozi-style editing**: Dynamic zoom cuts, silence removal, and audio
          normalization for maximum viewer retention.
        - **Word-synced subtitles**: Auto-generated captions synced to speech.
        - **Premiere Pro export**: Generates FCP XML for manual fine-tuning.

    Example:
        >>> from core.jarvis import get_jarvis
        >>> jarvis = get_jarvis()
        >>> result = jarvis.process(
        ...     "Create viral reels from this video",
        ...     video_path="/path/to/video.mp4",
        ...     output_dir="/path/to/output",
        ...     num_reels=5
        ... )
        >>> print(result.data["reels"])  # List of generated reel paths

    Configuration:
        All settings are controlled via ``config.settings``:
        - ``target_reels``: Number of reels to generate (default: 8)
        - ``min_reel_duration`` / ``max_reel_duration``: Clip length bounds (15-40s)
        - ``output_width`` / ``output_height``: Output resolution (1080x1920)
        - ``whisper_model``: Transcription model (default: "large-v3")
        - ``ollama_model``: LLM for viral detection (default: "llama3.1:8b")

    Pipeline Steps:
        1. **Analyze video** - Extract metadata (duration, resolution, FPS)
        2. **Transcribe** - GPU-accelerated speech-to-text with word timestamps
        3. **Find viral moments** - AI analysis for high-engagement segments
        4. **Detect faces** - YOLOv8 person tracking for smart cropping
        5. **Generate reels** - FFmpeg processing with effects and subtitles
        6. **Export XML** - Premiere Pro project file for further editing

    Attributes:
        transcriber: Cached faster-whisper model instance (lazy-loaded).
        yolo_model: Cached YOLOv8 model instance (lazy-loaded).
        TASK_KEYWORDS: List of keywords that trigger this module.
    """

    name = "video_editor"
    description = "Creates viral short-form content from long videos"
    version = "0.1.0"

    #: Keywords that indicate this module should handle the task
    TASK_KEYWORDS: list[str] = [
        "video", "reel", "clip", "edit", "cut", "shorts", "tiktok",
        "instagram", "youtube shorts", "viral", "transcribe"
    ]

    def __init__(self) -> None:
        """Initialize the VideoEditorModule.

        Models (Whisper, YOLO) are lazy-loaded on first use to minimize startup time.
        """
        super().__init__()
        self.transcriber = None
        self.yolo_model = None

    def can_handle(self, task: str) -> bool:
        """Check if this module can handle the given task.

        Performs case-insensitive keyword matching against TASK_KEYWORDS.

        Args:
            task: The task description string from the user.

        Returns:
            True if any video-related keyword is found in the task.
        """
        task_lower = task.lower()
        return any(kw in task_lower for kw in self.TASK_KEYWORDS)

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate that required inputs are present and valid.

        Args:
            **kwargs: Task parameters. Required:
                - video_path: Path to the source video file.

        Returns:
            A tuple of (is_valid, error_message). If valid, error_message is None.
        """
        video_path = kwargs.get("video_path")
        if not video_path:
            return False, "video_path is required"

        path = Path(video_path)
        if not path.exists():
            return False, f"Video file not found: {video_path}"

        return True, None

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute the full video editing pipeline.

        This is the main entry point for video processing. It runs all pipeline
        stages sequentially and returns the generated reels.

        Args:
            task: The task description (used for logging).
            **kwargs: Pipeline parameters:
                - video_path (str | Path): Path to source video. **Required**.
                - output_dir (str | Path): Directory for output files.
                  Defaults to ``settings.output_dir``.
                - num_reels (int): Number of reels to generate.
                  Defaults to ``settings.target_reels``.
                - language (str | None): Language code for transcription.
                  None = auto-detect.
                - shakshuka (bool): Enable Shakshuka mode (mashup + mini reels).

        Returns:
            TaskResult with:
                - success: True if all reels were generated successfully.
                - data: Dict containing:
                    - reels: List of output file paths.
                    - xml_project: Path to Premiere Pro XML file.
                    - moments: List of detected viral moments with timestamps.
                - error: Error message if processing failed.

        Raises:
            RuntimeError: If required dependencies (faster-whisper, ollama) are missing.
        """
        video_path = Path(kwargs["video_path"])
        output_dir = Path(kwargs.get("output_dir", settings.output_dir))
        num_reels = kwargs.get("num_reels", settings.target_reels)
        language = kwargs.get("language")  # None = auto-detect
        shakshuka = kwargs.get("shakshuka", False)

        output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Processing video: {video_path.name}")
        self.logger.info(f"Target reels: {num_reels}")

        try:
            # Step 1: Get video info
            self.logger.info("[1/6] Analyzing video...")
            video_info = self._get_video_info(video_path)
            self.logger.info(f"Duration: {video_info['duration']:.1f}s, Resolution: {video_info['width']}x{video_info['height']}")

            # Step 2: Transcribe with word-level timestamps
            lang_str = language if language else "auto-detect"
            self.logger.info(f"[2/6] Transcribing audio (GPU, lang={lang_str})...")
            segments = self._transcribe(video_path, language=language)
            self.logger.info(f"Transcribed {len(segments)} segments")

            # Step 3: Find viral moments with AI
            self.logger.info("[3/6] Finding viral moments (AI)...")
            moments = self._find_viral_moments(segments, num_reels)
            self.logger.info(f"Found {len(moments)} viral moments")

            # Step 4: Detect faces for smart cropping
            self.logger.info("[4/6] Detecting faces for smart crop...")
            face_data = self._detect_faces(video_path, moments)

            # Step 5: Generate reels (or Shakshuka mode)
            if shakshuka:
                self.logger.info("[5/6] Generating Shakshuka mashup...")
                reel_paths = self._create_shakshuka(
                    video_path=video_path,
                    output_dir=output_dir,
                    segments=segments,
                    moments=moments[:3],  # Top 3 moments for mini reels
                    face_data=face_data,
                    video_info=video_info
                )
            else:
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

    def _get_video_info(self, video_path: Path) -> VideoInfo:
        """Get video metadata using ffprobe"""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)

        video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
        return {
            "duration": float(data["format"]["duration"]),
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "fps": eval(video_stream.get("r_frame_rate", "30/1")),
        }

    def _transcribe(self, video_path: Path, language: Optional[str] = None) -> list[Segment]:
        """Transcribe video with faster-whisper (GPU accelerated).

        Args:
            video_path: Path to the video file.
            language: Language code (e.g., 'en', 'he', 'es'). None = auto-detect.
        """
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

        segments_raw, info = self.transcriber.transcribe(
            str(video_path),
            word_timestamps=True,
            language=language  # None = auto-detect
        )

        if language is None:
            self.logger.info(f"Detected language: {info.language} (prob: {info.language_probability:.2f})")

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

    # Hook detection patterns (questions, bold statements, calls to action)
    HOOK_PATTERNS: list[str] = [
        r"^(why|what|how|when|where|who|which|do you|did you|have you|can you|would you)",
        r"^(here'?s? (the|a|my)|let me (tell|show|explain))",
        r"^(the (secret|truth|problem|key|reason|best|worst|biggest|most))",
        r"^(i'?m going to|i want to|you need to|you should|you have to)",
        r"^(stop|wait|listen|look|think about|imagine|picture this)",
        r"^(number one|first|the first thing|step one)",
        r"(changed my life|game changer|mind blown|this is huge|nobody|everyone|always|never)",
        r"\?$",  # Ends with question mark
    ]

    def _score_segment_hook(self, text: str) -> float:
        """Score a segment for hook potential (0-10)."""
        text_lower = text.lower().strip()
        score = 0.0

        for pattern in self.HOOK_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                score += 2.0

        # Bonus for shorter punchy sentences
        word_count = len(text.split())
        if 5 <= word_count <= 15:
            score += 1.0

        # Bonus for questions
        if text.strip().endswith("?"):
            score += 1.5

        return min(score, 10.0)

    def _find_speech_boundaries(self, segments: list[Segment]) -> list[tuple[float, float, float]]:
        """Find natural speech boundaries based on pauses and sentence structure.

        Returns list of (start, end, pause_duration) tuples for potential cut points.
        """
        boundaries = []

        for i, seg in enumerate(segments):
            # Check for sentence-ending punctuation
            text = seg.text.strip()
            is_sentence_end = text.endswith(('.', '!', '?', '...'))

            # Calculate pause after this segment
            pause = 0.0
            if i < len(segments) - 1:
                pause = segments[i + 1].start - seg.end

            # Score this as a cut point
            if is_sentence_end or pause > 0.3:
                boundaries.append((seg.start, seg.end, pause))

        return boundaries

    def _fallback_moment_detection(self, segments: list[Segment], num_moments: int) -> list[ViralMoment]:
        """Fallback: find best moments using hook patterns and speech boundaries."""
        if not segments:
            return []

        # Find all natural speech boundaries
        boundaries = self._find_speech_boundaries(segments)

        # Score each potential clip
        candidates = []
        i = 0

        while i < len(segments):
            seg = segments[i]

            # Score this segment as a hook
            hook_score = self._score_segment_hook(seg.text)

            # Find the best end point for a 15-40 second clip
            clip_start = seg.start
            best_end = None
            best_end_score = 0.0

            for j in range(i, len(segments)):
                end_seg = segments[j]
                duration = end_seg.end - clip_start

                if duration < settings.min_reel_duration:
                    continue
                if duration > settings.max_reel_duration:
                    break

                # Score this end point
                end_text = end_seg.text.strip()
                end_score = 0.0

                # Prefer sentence endings
                if end_text.endswith(('.', '!', '?')):
                    end_score += 2.0

                # Prefer natural pauses
                if j < len(segments) - 1:
                    pause = segments[j + 1].start - end_seg.end
                    if pause > 0.5:
                        end_score += 1.5
                    elif pause > 0.3:
                        end_score += 1.0

                # Prefer clips closer to 25-35 seconds (sweet spot)
                if 25 <= duration <= 35:
                    end_score += 1.0

                if end_score > best_end_score:
                    best_end = end_seg.end
                    best_end_score = end_score

            if best_end and best_end > clip_start:
                candidates.append(ViralMoment(
                    start=clip_start,
                    end=best_end,
                    score=hook_score + best_end_score,
                    reason="Hook pattern + natural boundary",
                    hook=seg.text[:50] if seg.text else ""
                ))
                # Skip past this clip to avoid overlap
                while i < len(segments) and segments[i].end <= best_end:
                    i += 1
            else:
                i += 1

        # Sort by score (best first) and return top N non-overlapping
        candidates.sort(key=lambda x: x.score, reverse=True)

        selected = []
        for cand in candidates:
            # Check for overlap with already selected
            overlaps = False
            for sel in selected:
                if not (cand.end <= sel.start or cand.start >= sel.end):
                    overlaps = True
                    break
            if not overlaps:
                selected.append(cand)
                if len(selected) >= num_moments:
                    break

        return selected

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
            # Sample frames throughout the moment
            sample_times = [
                moment.start,
                (moment.start + moment.end) / 2,
                moment.end - 0.5
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
        video_info: VideoInfo
    ) -> None:
        """Create a single reel with all effects"""

        # Calculate crop region (center on face or center of frame)
        src_w, src_h = video_info["width"], video_info["height"]
        target_w, target_h = settings.output_width, settings.output_height
        target_ratio = target_w / target_h  # 9:16 = 0.5625

        if face_data:
            # Average face position
            avg_x = sum(f.x + f.width/2 for f in face_data) / len(face_data)
            avg_y = sum(f.y + f.height/2 for f in face_data) / len(face_data)
            center_x, center_y = int(avg_x), int(avg_y)
        else:
            center_x, center_y = src_w // 2, src_h // 2

        # Calculate crop dimensions to get 9:16
        if src_w / src_h > target_ratio:
            # Video is wider - crop width
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            # Video is taller - crop height
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)

        # Center crop on face/center, bounded to frame
        crop_x = max(0, min(center_x - crop_w // 2, src_w - crop_w))
        crop_y = max(0, min(center_y - crop_h // 2, src_h - crop_h))

        # Create subtitle filter
        subtitle_filter = self._create_subtitle_filter(words, moment.start)

        # Build FFmpeg filter complex for Hormozi-style editing
        filter_complex = self._build_filter_complex(
            crop_x, crop_y, crop_w, crop_h,
            target_w, target_h,
            moment.end - moment.start,
            subtitle_filter
        )

        # Build FFmpeg command with GPU encoding
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
            "-c:a", settings.audio_codec,
            "-b:a", settings.audio_bitrate,
            "-movflags", "+faststart",
            str(output_path)
        ]

        self.logger.debug(f"Running FFmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Try with CPU encoding as fallback
            self.logger.warning("GPU encoding failed, trying CPU...")
            cmd[cmd.index("-c:v") + 1] = "libx264"
            cmd.remove("-preset")
            cmd.remove(settings.ffmpeg_preset)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    def _create_shakshuka(
        self,
        video_path: Path,
        output_dir: Path,
        segments: list[Segment],
        moments: list[ViralMoment],
        face_data: dict[int, list[FaceDetection]],
        video_info: VideoInfo
    ) -> list[Path]:
        """Create Shakshuka mode output: word mashup + 3 mini reels.

        Shakshuka mode generates:
        1. A rapid-fire word mashup (10-15 seconds) with punchy words
        2. 3 mini reels from the top viral moments

        Returns list of generated file paths.
        """
        output_paths = []

        # Collect all words from segments
        all_words = []
        for seg in segments:
            all_words.extend(seg.words)

        # Step 1: Create word mashup
        self.logger.info("Creating word mashup...")
        mashup_path = output_dir / "shakshuka_mashup.mp4"
        self._create_word_mashup(video_path, mashup_path, all_words, video_info, face_data)
        output_paths.append(mashup_path)

        # Step 2: Create 3 mini reels from top moments
        for i, moment in enumerate(moments[:3]):
            self.logger.info(f"Creating mini reel {i+1}/3...")
            reel_path = output_dir / f"shakshuka_reel_{i+1:02d}.mp4"
            words_for_moment = self._get_words_for_timerange(segments, moment.start, moment.end)
            self._create_reel(
                video_path=video_path,
                output_path=reel_path,
                moment=moment,
                words=words_for_moment,
                face_data=face_data.get(i, []),
                video_info=video_info
            )
            output_paths.append(reel_path)

        return output_paths

    def _create_word_mashup(
        self,
        video_path: Path,
        output_path: Path,
        words: list[Word],
        video_info: VideoInfo,
        face_data: dict[int, list[FaceDetection]]
    ) -> None:
        """Create a rapid-fire word mashup from powerful words."""
        # Power words to look for (high-impact vocabulary)
        power_patterns = [
            r"^(amazing|incredible|insane|crazy|huge|massive|best|worst|secret|truth)$",
            r"^(money|success|rich|wealth|power|freedom|love|hate|fear|win|lose)$",
            r"^(now|today|always|never|everyone|nobody|everything|nothing)$",
            r"^(stop|start|go|run|fight|build|create|destroy|change|grow)$",
            r"^(why|what|how|who|when|where)$",
        ]

        # Find power words with good timestamps
        power_words = []
        for word in words:
            text = word.text.lower().strip()
            for pattern in power_patterns:
                if re.match(pattern, text):
                    power_words.append(word)
                    break

        # If not enough power words, add random high-confidence words
        if len(power_words) < 15:
            other_words = [w for w in words if w not in power_words and w.confidence > 0.9]
            # Sort by confidence and take top words
            other_words.sort(key=lambda w: w.confidence, reverse=True)
            power_words.extend(other_words[:15 - len(power_words)])

        # Limit to ~15-20 words for 10-15 second mashup
        power_words = power_words[:20]

        if len(power_words) < 5:
            self.logger.warning("Not enough words for mashup, skipping")
            return

        # Calculate crop parameters
        src_w, src_h = video_info["width"], video_info["height"]
        target_w, target_h = settings.output_width, settings.output_height
        target_ratio = target_w / target_h

        # Use first face detection or center
        all_faces = [f for faces in face_data.values() for f in faces]
        if all_faces:
            avg_x = sum(f.x + f.width/2 for f in all_faces) / len(all_faces)
            avg_y = sum(f.y + f.height/2 for f in all_faces) / len(all_faces)
            center_x, center_y = int(avg_x), int(avg_y)
        else:
            center_x, center_y = src_w // 2, src_h // 2

        if src_w / src_h > target_ratio:
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)

        crop_x = max(0, min(center_x - crop_w // 2, src_w - crop_w))
        crop_y = max(0, min(center_y - crop_h // 2, src_h - crop_h))

        # Create concat file for FFmpeg
        concat_file = output_path.parent / "concat_list.txt"
        temp_clips = []

        with open(concat_file, 'w') as f:
            for i, word in enumerate(power_words):
                # Extract each word as a clip (with 0.1s padding for impact)
                clip_path = output_path.parent / f"_temp_word_{i:03d}.mp4"
                temp_clips.append(clip_path)

                duration = max(0.3, word.end - word.start + 0.15)  # Min 0.3s per word
                start_time = max(0, word.start - 0.05)  # Small lead-in

                # Quick clip extraction with crop
                clip_cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(start_time),
                    "-i", str(video_path),
                    "-t", str(duration),
                    "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={target_w}:{target_h}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    str(clip_path)
                ]
                subprocess.run(clip_cmd, capture_output=True)
                f.write(f"file '{clip_path}'\n")

        # Concatenate all clips
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", settings.video_codec,
            "-preset", settings.ffmpeg_preset,
            "-crf", str(settings.ffmpeg_crf),
            "-c:a", settings.audio_codec,
            "-b:a", settings.audio_bitrate,
            "-movflags", "+faststart",
            str(output_path)
        ]

        result = subprocess.run(concat_cmd, capture_output=True, text=True)

        # Cleanup temp files
        for clip in temp_clips:
            if clip.exists():
                clip.unlink()
        if concat_file.exists():
            concat_file.unlink()

        if result.returncode != 0:
            self.logger.warning(f"Mashup creation failed: {result.stderr[:200]}")

    def _create_subtitle_filter(self, words: list[Word], offset: float) -> str:
        """Create drawtext filter for word-synced subtitles"""
        if not words:
            return ""

        filters = []
        chunk_size = settings.subtitle_words_per_chunk

        for i in range(0, len(words), chunk_size):
            chunk = words[i:i+chunk_size]
            text = " ".join(w.text for w in chunk)
            # Escape special characters for FFmpeg
            text = text.replace("'", "'\\''").replace(":", "\\:")
            start = chunk[0].start - offset
            end = chunk[-1].end - offset

            filters.append(
                f"drawtext=text='{text}':"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"fontsize={settings.subtitle_font_size}:"
                f"fontcolor={settings.subtitle_color}:"
                f"bordercolor={settings.subtitle_stroke_color}:"
                f"borderw={settings.subtitle_stroke_width}:"
                f"x=(w-text_w)/2:y=h*0.75:"
                f"enable='between(t,{start:.3f},{end:.3f})'"
            )

        return ",".join(filters)

    def _build_filter_complex(
        self,
        crop_x: int, crop_y: int, crop_w: int, crop_h: int,
        target_w: int, target_h: int,
        duration: float,
        subtitle_filter: str
    ) -> str:
        """Build FFmpeg filter complex with Hormozi-style cuts"""

        # Calculate zoom segments
        cut_interval = (settings.cut_interval_min + settings.cut_interval_max) / 2
        num_cuts = int(duration / cut_interval)

        # Base video processing
        video_filters = [
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            f"scale={target_w}:{target_h}:flags=lanczos"
        ]

        # Add zoom pulses (Hormozi style)
        zoom_factor = settings.zoom_factor
        for i in range(num_cuts):
            t_start = i * cut_interval
            t_end = t_start + 0.2  # Quick zoom

            # zoompan for zoom effect
            video_filters.append(
                f"zoompan=z='if(between(time,{t_start:.2f},{t_end:.2f}),{zoom_factor},1)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d=1:s={target_w}x{target_h}:fps={settings.fps}"
            )

        # Add subtitles
        if subtitle_filter:
            video_filters.append(subtitle_filter)

        video_chain = ",".join(video_filters) + "[outv]"

        # Audio processing: normalize and remove silence
        audio_filters = [
            "loudnorm=I=-16:TP=-1.5:LRA=11",  # Normalize audio
            f"silenceremove=start_periods=1:start_duration=0.1:start_threshold={settings.silence_threshold}dB:"
            f"detection=peak:stop_periods=-1:stop_duration={settings.silence_min_duration}:"
            f"stop_threshold={settings.silence_threshold}dB"
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
        for i, moment in enumerate(moments):
            xml_content += f'''              <clipitem id="clip{i+1}">
                <name>Reel {i+1}</name>
                <start>{int(moment.start * 30)}</start>
                <end>{int(moment.end * 30)}</end>
                <in>{int(moment.start * 30)}</in>
                <out>{int(moment.end * 30)}</out>
                <file>
                  <pathurl>file://{video_path}</pathurl>
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
