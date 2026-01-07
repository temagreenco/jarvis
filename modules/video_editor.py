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


# ============================================================
# VIRAL CONTENT ANALYSIS PATTERNS
# ============================================================

# Viral trigger words (Hebrew + English)
VIRAL_TRIGGERS = {
    "hebrew": {
        "high_value": ["סוד", "אמת", "אף אחד לא מספר", "טעות", "בעצם", "הנה העניין",
                       "משנה חיים", "סוף סוף", "חייבים לדעת", "פלוט טוויסט"],
        "curiosity": ["אבל הנה הבעיה", "עד שהבנתי", "ואז הכל השתנה", "מה שקרה אחר כך"],
        "authority": ["אחרי 10 שנים", "השקעתי", "עבדתי עם", "המחקר מראה", "הנתונים מוכיחים"],
        "urgency": ["עכשיו", "לפני שיהיה מאוחר", "רוב האנשים אף פעם", "תפסיקו לעשות", "חייבים לשמוע"],
    },
    "english": {
        "high_value": ["secret", "truth", "nobody tells you", "mistake", "actually",
                       "here's the thing", "plot twist", "game changer", "life changing"],
        "curiosity": ["but here's the problem", "until I realized", "everything changed", "what happened next"],
        "authority": ["after 10 years", "I've spent", "working with", "data shows", "research proves"],
        "urgency": ["right now", "before it's too late", "most people never", "stop doing this", "you need to hear"],
    }
}

# Hook patterns with scoring weights
HOOK_PATTERNS = [
    (r"(?:nobody|no one).{0,20}(?:tells|knows|talks)", 30, "controversial_opener"),
    (r"(?:why|how|what).{0,30}\?", 25, "question_hook"),
    (r"(?:so there I was|let me tell you|story time)", 25, "story_hook"),
    (r"\d+%|\$\d+|only \d+", 20, "statistic_shock"),
    (r"(?:stop scrolling|wait|hold on|listen)", 20, "pattern_interrupt"),
    # Hebrew patterns
    (r"אף אחד לא", 30, "controversial_opener_he"),
    (r"למה|איך|מה\s", 25, "question_hook_he"),
    (r"סיפור|פעם אחת", 25, "story_hook_he"),
]


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
    # Detailed score breakdown
    hook_score: float = 0.0
    content_score: float = 0.0
    energy_score: float = 0.0
    ending_score: float = 0.0
    detected_hooks: list = field(default_factory=list)
    detected_triggers: list = field(default_factory=list)


# ============================================================
# VIRALITY SCORING FUNCTIONS
# ============================================================

def analyze_hook_strength(text: str, first_n_words: int = 10) -> tuple[float, list[str]]:
    """Analyze hook strength of first few words. Returns (score, detected_patterns)"""
    words = text.split()[:first_n_words]
    hook_text = ' '.join(words).lower()
    score = 0.0
    detected = []

    for pattern, weight, name in HOOK_PATTERNS:
        if re.search(pattern, hook_text, re.IGNORECASE):
            score += weight
            detected.append(name)

    return min(30, score), detected


def count_viral_triggers(text: str) -> tuple[float, list[str]]:
    """Count viral trigger words/phrases. Returns (score, found_triggers)"""
    score = 0.0
    found = []
    text_lower = text.lower()

    for lang in ['hebrew', 'english']:
        for category, triggers in VIRAL_TRIGGERS.get(lang, {}).items():
            for trigger in triggers:
                if trigger.lower() in text_lower:
                    score += 5
                    found.append(trigger)

    return min(25, score), found


def analyze_engagement_patterns(text: str) -> float:
    """Detect engagement patterns in text. Returns score 0-25."""
    score = 0.0
    text_lower = text.lower()

    # Complete thought (ends with conclusion)
    if re.search(r'(so|therefore|that\'s why|לכן|אז|זה למה)', text_lower):
        score += 15

    # Actionable advice
    if re.search(r'(you should|try this|do this|תעשו|נסו|צריך ל)', text_lower):
        score += 20

    # Specific numbers
    if re.search(r'\d+', text):
        score += 10

    # Transformation language
    if re.search(r'(before|after|changed|became|הפך|השתנה|לפני|אחרי)', text_lower):
        score += 25

    # Contrast/conflict
    if re.search(r'(but|however|although|אבל|למרות|אף על פי)', text_lower):
        score += 15

    return min(25, score)


def analyze_ending_strength(text: str) -> float:
    """Analyze ending strength. Returns score -10 to +5."""
    words = text.split()[-5:]
    ending = ' '.join(words).lower()

    # Weak endings get penalty
    weak_patterns = [r'(um|uh|like|אה|אמ|כאילו)$', r'\.\.\.$', r'and$']
    for pattern in weak_patterns:
        if re.search(pattern, ending):
            return -10

    # Strong endings get bonus
    strong_patterns = [r'[!?]$', r'(right|exactly|נכון|בדיוק)$']
    for pattern in strong_patterns:
        if re.search(pattern, ending):
            return 5

    return 0


def calculate_virality_score(text: str) -> tuple[float, dict]:
    """Calculate total virality score for text. Returns (score, breakdown)."""
    hook_score, hooks = analyze_hook_strength(text)
    trigger_score, triggers = count_viral_triggers(text)
    energy_score = analyze_engagement_patterns(text)
    ending_score = analyze_ending_strength(text)

    total = hook_score + trigger_score + energy_score + ending_score
    total = max(0, min(100, total))

    breakdown = {
        "hook_score": hook_score,
        "content_score": trigger_score,
        "energy_score": energy_score,
        "ending_score": ending_score,
        "detected_hooks": hooks,
        "detected_triggers": triggers
    }

    return total, breakdown


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
    version = "0.1.0"

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

            # Step 5: Generate reels with thumbnails and SRT
            self.logger.info("[5/7] Generating reels...")
            reel_data = []
            for i, moment in enumerate(moments):
                self.logger.info(f"Creating reel {i+1}/{len(moments)}: {moment.hook[:50]}...")

                # Generate file paths
                reel_name = f"reel_{i+1:02d}_score{int(moment.score)}"
                reel_path = output_dir / f"{reel_name}.mp4"
                thumb_path = output_dir / f"{reel_name}_thumb.jpg"
                srt_path = output_dir / f"{reel_name}.srt"

                words_for_moment = self._get_words_for_timerange(segments, moment.start, moment.end)

                # Create the reel video
                self._create_reel(
                    video_path=video_path,
                    output_path=reel_path,
                    moment=moment,
                    words=words_for_moment,
                    face_data=face_data.get(i, []),
                    video_info=video_info
                )

                # Generate thumbnail (at 30% into the reel)
                self._extract_thumbnail(reel_path, thumb_path)

                # Generate SRT file (with adjusted timestamps)
                adjusted_words = [
                    Word(text=w.text, start=w.start - moment.start, end=w.end - moment.start, confidence=w.confidence)
                    for w in words_for_moment
                ]
                self._generate_srt(adjusted_words, srt_path)

                reel_data.append({
                    "video": str(reel_path),
                    "thumbnail": str(thumb_path),
                    "srt": str(srt_path),
                    "moment": moment
                })

            # Step 6: Generate Premiere Pro XML
            self.logger.info("[6/7] Generating Premiere Pro XML...")
            xml_path = output_dir / "project.xml"
            self._generate_premiere_xml(video_path, moments, xml_path)

            # Step 7: Save metadata JSON
            self.logger.info("[7/7] Saving metadata...")
            metadata_path = output_dir / "reels_metadata.json"
            self._save_metadata(video_path, moments, reel_data, metadata_path)

            return TaskResult(
                success=True,
                data={
                    "reels": [r["video"] for r in reel_data],
                    "thumbnails": [r["thumbnail"] for r in reel_data],
                    "subtitles": [r["srt"] for r in reel_data],
                    "xml_project": str(xml_path),
                    "metadata": str(metadata_path),
                    "moments": [
                        {
                            "start": m.start,
                            "end": m.end,
                            "hook": m.hook,
                            "score": m.score,
                            "score_breakdown": {
                                "hook": m.hook_score,
                                "content": m.content_score,
                                "energy": m.energy_score,
                                "ending": m.ending_score
                            },
                            "detected_hooks": m.detected_hooks,
                            "detected_triggers": m.detected_triggers
                        }
                        for m in moments
                    ]
                },
                metadata={"video": str(video_path), "num_reels": len(reel_data)}
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
        data = json.loads(result.stdout)

        video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")

        # Safe fps parsing (avoid eval)
        fps_str = video_stream.get("r_frame_rate", "30/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(fps_str)

        return {
            "duration": float(data["format"]["duration"]),
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
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

        # Use configured language (None for auto-detect)
        lang = settings.whisper_language if settings.whisper_language else None
        segments_raw, info = self.transcriber.transcribe(
            str(video_path),
            word_timestamps=True,
            language=lang
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
        """Rule-based viral moment detection (works without Ollama)"""
        if not segments:
            return []

        self.logger.info("Using rule-based virality analysis...")
        candidates = []

        # Build candidate segments from natural breaks
        current_start = 0.0
        current_text = []

        for i, seg in enumerate(segments):
            current_text.append(seg.text)
            duration = seg.end - current_start

            # Check if we have a good segment
            if duration >= settings.min_reel_duration:
                is_break_point = False

                # Natural pause between segments
                if i < len(segments) - 1:
                    gap = segments[i + 1].start - seg.end
                    if gap > 0.5:
                        is_break_point = True

                # Sentence end
                if seg.text.strip().endswith(('.', '!', '?', '。')):
                    is_break_point = True

                # Duration limit
                if duration >= settings.max_reel_duration:
                    is_break_point = True

                if is_break_point:
                    full_text = ' '.join(current_text)
                    score, breakdown = calculate_virality_score(full_text)

                    candidates.append(ViralMoment(
                        start=current_start,
                        end=seg.end,
                        score=score,
                        reason=f"Rule-based (hooks: {len(breakdown['detected_hooks'])}, triggers: {len(breakdown['detected_triggers'])})",
                        hook=full_text[:50] if full_text else "",
                        hook_score=breakdown['hook_score'],
                        content_score=breakdown['content_score'],
                        energy_score=breakdown['energy_score'],
                        ending_score=breakdown['ending_score'],
                        detected_hooks=breakdown['detected_hooks'],
                        detected_triggers=breakdown['detected_triggers']
                    ))

                    current_start = segments[i + 1].start if i < len(segments) - 1 else seg.end
                    current_text = []

        # Sort by virality score and select top non-overlapping
        candidates.sort(key=lambda m: m.score, reverse=True)

        selected = []
        for candidate in candidates:
            # Check for overlap with already selected
            overlaps = False
            for existing in selected:
                if not (candidate.end <= existing.start or candidate.start >= existing.end):
                    overlaps = True
                    break

            if not overlaps:
                selected.append(candidate)

            if len(selected) >= num_moments:
                break

        # Sort by time for output
        selected.sort(key=lambda m: m.start)

        self.logger.info(f"Found {len(selected)} segments via rule-based analysis")
        for m in selected:
            self.logger.debug(f"  [{m.start:.1f}s-{m.end:.1f}s] Score: {m.score:.0f} - {m.hook[:30]}...")

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
        video_info: dict
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

    def _extract_thumbnail(self, video_path: Path, output_path: Path, time: float = None) -> Path:
        """Extract a thumbnail frame from the video"""
        if time is None:
            # Get video duration and extract at 30%
            info = self._get_video_info(video_path)
            time = info['duration'] * 0.3

        cmd = [
            'ffmpeg', '-y',
            '-ss', str(time),
            '-i', str(video_path),
            '-vframes', '1',
            '-q:v', '2',
            str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.logger.warning(f"Thumbnail extraction failed: {result.stderr}")
            return None

        self.logger.debug(f"Thumbnail saved: {output_path}")
        return output_path

    def _generate_srt(self, words: list[Word], output_path: Path, max_chars: int = 40) -> Path:
        """Generate SRT subtitle file from word timestamps"""
        srt_lines = []
        index = 1
        current_line = []
        line_start = None

        for word in words:
            if line_start is None:
                line_start = word.start

            current_line.append(word.text.strip())
            current_text = ' '.join(current_line)

            # Break line if too long or at punctuation
            should_break = (
                len(current_text) > max_chars or
                word.text.strip().endswith(('.', '?', '!', ','))
            )

            if should_break and current_line:
                start_tc = self._format_srt_time(line_start)
                end_tc = self._format_srt_time(word.end)

                srt_lines.append(f"{index}")
                srt_lines.append(f"{start_tc} --> {end_tc}")
                srt_lines.append(current_text.strip())
                srt_lines.append("")

                index += 1
                current_line = []
                line_start = None

        # Handle remaining words
        if current_line:
            start_tc = self._format_srt_time(line_start)
            end_tc = self._format_srt_time(words[-1].end)
            srt_lines.append(f"{index}")
            srt_lines.append(f"{start_tc} --> {end_tc}")
            srt_lines.append(' '.join(current_line).strip())
            srt_lines.append("")

        output_path.write_text('\n'.join(srt_lines), encoding='utf-8')
        self.logger.debug(f"SRT saved: {output_path}")
        return output_path

    def _format_srt_time(self, seconds: float) -> str:
        """Format seconds to SRT timestamp (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _save_metadata(self, video_path: Path, moments: list[ViralMoment], reel_data: list, output_path: Path) -> None:
        """Save comprehensive metadata JSON"""
        from datetime import datetime

        metadata = {
            "generated_at": datetime.now().isoformat(),
            "source_video": str(video_path),
            "config": {
                "min_duration": settings.min_reel_duration,
                "max_duration": settings.max_reel_duration,
                "target_reels": settings.target_reels,
                "output_resolution": f"{settings.output_width}x{settings.output_height}"
            },
            "reels": []
        }

        for i, (moment, data) in enumerate(zip(moments, reel_data)):
            reel_info = {
                "id": f"reel_{i+1:02d}",
                "source_timecode": {
                    "start": self._format_timecode(moment.start),
                    "end": self._format_timecode(moment.end)
                },
                "duration": round(moment.end - moment.start, 3),
                "virality_score": round(moment.score, 1),
                "score_breakdown": {
                    "hook_strength": round(moment.hook_score, 1),
                    "content_quality": round(moment.content_score, 1),
                    "energy": round(moment.energy_score, 1),
                    "ending": round(moment.ending_score, 1)
                },
                "detected_hooks": moment.detected_hooks,
                "viral_triggers": moment.detected_triggers,
                "reason": moment.reason,
                "hook_preview": moment.hook[:100] if moment.hook else "",
                "output_files": {
                    "video": data["video"],
                    "thumbnail": data["thumbnail"],
                    "subtitles": data["srt"]
                }
            }
            metadata["reels"].append(reel_info)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Metadata saved: {output_path}")

    def _format_timecode(self, seconds: float) -> str:
        """Format seconds to HH:MM:SS.mmm timecode"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
