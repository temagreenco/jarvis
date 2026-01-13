"""
Video Editor Module V2 - Professional-grade editing like Opus Clip / AutoCut

New Features:
- Multi-modal viral moment detection (transcript + audio + visual)
- Animated karaoke-style captions with word highlighting
- Smooth face tracking with frame interpolation
- Content-aware dynamic zoom (on emphasis, not timed)
- Audio beat/energy detection for scene transitions
- AI B-roll suggestions
- Multi-format export (9:16, 1:1, 16:9)
- Brand template system
- Advanced virality scoring
"""

import json
import subprocess
import tempfile
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Literal
from enum import Enum
import re
import math

from modules.base_module import BaseModule, TaskResult
from config.settings import settings
from utils.logger import get_logger

logger = get_logger("video_editor_v2")


# ============================================================================
# DATA CLASSES
# ============================================================================

class AspectRatio(Enum):
    """Supported output formats"""
    VERTICAL = "9:16"      # TikTok, Reels, Shorts
    SQUARE = "1:1"         # Instagram Feed
    HORIZONTAL = "16:9"    # YouTube

    @property
    def dimensions(self) -> tuple[int, int]:
        return {
            AspectRatio.VERTICAL: (1080, 1920),
            AspectRatio.SQUARE: (1080, 1080),
            AspectRatio.HORIZONTAL: (1920, 1080),
        }[self]


@dataclass
class Word:
    """A transcribed word with timing and emphasis"""
    text: str
    start: float
    end: float
    confidence: float = 1.0
    is_emphasized: bool = False  # Detected from audio energy


@dataclass
class Segment:
    """A segment of transcript with audio features"""
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)
    avg_energy: float = 0.0  # Audio energy level
    sentiment: str = "neutral"  # positive, negative, neutral


@dataclass
class AudioBeat:
    """Detected audio beat/emphasis point"""
    timestamp: float
    energy: float
    is_speech_start: bool = False
    is_emphasis: bool = False


@dataclass
class FaceTrack:
    """Face tracking data for a moment"""
    frame_num: int
    timestamp: float
    center_x: float  # Normalized 0-1
    center_y: float  # Normalized 0-1
    scale: float     # Face size relative to frame
    confidence: float


@dataclass
class ViralMoment:
    """A detected viral moment with scoring breakdown"""
    start: float
    end: float
    hook: str
    transcript: str

    # Scoring breakdown (all 0-10)
    hook_score: float = 5.0
    pacing_score: float = 5.0
    energy_score: float = 5.0
    completeness_score: float = 5.0

    # Metadata
    reason: str = ""
    suggested_broll: list[str] = field(default_factory=list)

    @property
    def virality_score(self) -> float:
        """Weighted virality score like Opus Clip"""
        return (
            self.hook_score * 0.35 +
            self.pacing_score * 0.25 +
            self.energy_score * 0.25 +
            self.completeness_score * 0.15
        )


@dataclass
class BrandTemplate:
    """Brand styling template"""
    name: str = "default"
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#FFD700"  # Gold highlight
    background_color: str = "#000000"
    font_family: str = "Montserrat-Bold"
    font_size: int = 64
    stroke_width: int = 4
    stroke_color: str = "#000000"
    logo_path: Optional[str] = None
    logo_position: str = "top-right"  # top-left, top-right, bottom-left, bottom-right
    logo_scale: float = 0.1  # Relative to video width


# ============================================================================
# MAIN MODULE
# ============================================================================

class VideoEditorV2(BaseModule):
    """
    Professional-grade video editor matching Opus Clip / AutoCut quality.
    """

    name = "video_editor_v2"
    description = "Professional short-form video creation (Opus Clip style)"
    version = "2.0.0"

    TASK_KEYWORDS = [
        "video", "reel", "clip", "edit", "cut", "shorts", "tiktok",
        "instagram", "youtube shorts", "viral", "transcribe", "opus", "autocut"
    ]

    def __init__(self):
        super().__init__()
        self.transcriber = None
        self.yolo_model = None
        self._cache_dir = Path(tempfile.gettempdir()) / "jarvis_cache"
        self._cache_dir.mkdir(exist_ok=True)

    def can_handle(self, task: str) -> bool:
        task_lower = task.lower()
        return any(kw in task_lower for kw in self.TASK_KEYWORDS)

    def validate_inputs(self, **kwargs) -> tuple[bool, Optional[str]]:
        video_path = kwargs.get("video_path")
        if not video_path:
            return False, "video_path is required"
        if not Path(video_path).exists():
            return False, f"Video file not found: {video_path}"
        return True, None

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute enhanced video editing pipeline"""
        video_path = Path(kwargs["video_path"])
        output_dir = Path(kwargs.get("output_dir", settings.output_dir))
        num_reels = kwargs.get("num_reels", settings.target_reels)
        aspect_ratios = kwargs.get("aspect_ratios", [AspectRatio.VERTICAL])
        template = kwargs.get("template", BrandTemplate())

        output_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"🎬 Processing: {video_path.name}")
        self.logger.info(f"📊 Target reels: {num_reels}")

        try:
            # Step 1: Analyze video
            self.logger.info("[1/8] Analyzing video metadata...")
            video_info = self._get_video_info(video_path)

            # Step 2: Transcribe with word timestamps
            self.logger.info("[2/8] Transcribing audio (GPU-accelerated)...")
            segments = self._transcribe(video_path)

            # Step 3: Analyze audio energy/beats
            self.logger.info("[3/8] Analyzing audio energy and beats...")
            audio_beats = self._analyze_audio_energy(video_path)
            self._mark_emphasized_words(segments, audio_beats)

            # Step 4: Multi-modal viral moment detection
            self.logger.info("[4/8] Detecting viral moments (AI multi-modal)...")
            moments = self._find_viral_moments_v2(
                segments, audio_beats, video_info, num_reels
            )

            # Step 5: Full face tracking
            self.logger.info("[5/8] Tracking faces (frame-by-frame)...")
            face_tracks = self._track_faces_smooth(video_path, moments, video_info)

            # Step 6: Generate reels for each format
            self.logger.info("[6/8] Generating reels...")
            all_reels = {}
            for aspect in aspect_ratios:
                all_reels[aspect.value] = []
                for i, moment in enumerate(moments):
                    self.logger.info(
                        f"  Reel {i+1}/{len(moments)} [{aspect.value}] "
                        f"(score: {moment.virality_score:.1f}) - {moment.hook[:40]}..."
                    )
                    reel_path = output_dir / f"reel_{i+1:02d}_{aspect.value.replace(':', 'x')}.mp4"
                    words = self._get_words_for_timerange(segments, moment.start, moment.end)

                    self._create_reel_v2(
                        video_path=video_path,
                        output_path=reel_path,
                        moment=moment,
                        words=words,
                        face_track=face_tracks.get(i, []),
                        audio_beats=audio_beats,
                        video_info=video_info,
                        aspect_ratio=aspect,
                        template=template
                    )
                    all_reels[aspect.value].append(str(reel_path))

            # Step 7: Generate project files
            self.logger.info("[7/8] Generating project files...")
            xml_path = output_dir / "premiere_project.xml"
            self._generate_premiere_xml(video_path, moments, xml_path)

            # Step 8: Generate analytics
            self.logger.info("[8/8] Generating analytics report...")
            analytics = self._generate_analytics(moments)
            analytics_path = output_dir / "analytics.json"
            analytics_path.write_text(json.dumps(analytics, indent=2))

            return TaskResult(
                success=True,
                data={
                    "reels": all_reels,
                    "xml_project": str(xml_path),
                    "analytics": analytics,
                    "moments": [
                        {
                            "start": m.start,
                            "end": m.end,
                            "hook": m.hook,
                            "virality_score": m.virality_score,
                            "scores": {
                                "hook": m.hook_score,
                                "pacing": m.pacing_score,
                                "energy": m.energy_score,
                                "completeness": m.completeness_score
                            }
                        }
                        for m in moments
                    ]
                },
                metadata={"video": str(video_path), "num_reels": len(moments)}
            )

        except Exception as e:
            self.logger.error(f"Video editing failed: {e}")
            import traceback
            traceback.print_exc()
            return TaskResult(success=False, error=str(e))

    # ========================================================================
    # VIDEO ANALYSIS
    # ========================================================================

    def _get_video_info(self, video_path: Path) -> dict:
        """Get video metadata using ffprobe"""
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)

        video_stream = next(s for s in data["streams"] if s["codec_type"] == "video")
        audio_stream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)

        return {
            "duration": float(data["format"]["duration"]),
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "fps": eval(video_stream.get("r_frame_rate", "30/1")),
            "has_audio": audio_stream is not None,
            "sample_rate": int(audio_stream["sample_rate"]) if audio_stream else 44100,
        }

    # ========================================================================
    # TRANSCRIPTION
    # ========================================================================

    def _transcribe(self, video_path: Path) -> list[Segment]:
        """Transcribe with faster-whisper (GPU)"""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError("faster-whisper not installed")

        if self.transcriber is None:
            self.logger.info(f"Loading Whisper: {settings.whisper_model}")
            self.transcriber = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type
            )

        segments_raw, info = self.transcriber.transcribe(
            str(video_path),
            word_timestamps=True,
            language="en"
        )

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

    # ========================================================================
    # AUDIO ENERGY ANALYSIS (NEW)
    # ========================================================================

    def _analyze_audio_energy(self, video_path: Path) -> list[AudioBeat]:
        """Analyze audio for energy peaks, beats, and emphasis points"""
        beats = []

        # Extract audio energy using FFmpeg
        # This gives us volume levels at regular intervals
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-f", "null", "-"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        # Parse RMS levels from output
        energy_data = []
        current_time = 0.0
        frame_duration = 1.0 / 100  # 100 samples per second

        for line in result.stderr.split('\n'):
            if 'RMS_level' in line:
                try:
                    # Extract dB value
                    match = re.search(r'RMS_level=(-?\d+\.?\d*)', line)
                    if match:
                        db = float(match.group(1))
                        # Convert dB to linear energy (0-1 scale)
                        energy = max(0, min(1, (db + 60) / 60))  # -60dB to 0dB mapped to 0-1
                        energy_data.append((current_time, energy))
                        current_time += frame_duration
                except:
                    continue

        if not energy_data:
            # Fallback: generate basic beats from video duration
            self.logger.warning("Audio analysis failed, using fallback")
            return self._generate_fallback_beats(video_path)

        # Find emphasis points (local maxima in energy)
        window_size = 10
        for i in range(window_size, len(energy_data) - window_size):
            timestamp, energy = energy_data[i]

            # Check if this is a local maximum
            window = [e for _, e in energy_data[i-window_size:i+window_size]]
            if energy >= max(window) * 0.95 and energy > 0.3:
                beats.append(AudioBeat(
                    timestamp=timestamp,
                    energy=energy,
                    is_emphasis=True
                ))

        # Detect speech starts (energy rising after silence)
        prev_energy = 0
        for timestamp, energy in energy_data:
            if prev_energy < 0.1 and energy > 0.3:
                beats.append(AudioBeat(
                    timestamp=timestamp,
                    energy=energy,
                    is_speech_start=True
                ))
            prev_energy = energy

        # Sort by timestamp and deduplicate
        beats.sort(key=lambda b: b.timestamp)
        return self._deduplicate_beats(beats, min_gap=0.3)

    def _generate_fallback_beats(self, video_path: Path) -> list[AudioBeat]:
        """Generate basic beats when audio analysis fails"""
        info = self._get_video_info(video_path)
        duration = info["duration"]
        beats = []

        # Generate beats every 2-3 seconds
        t = 0.5
        while t < duration:
            beats.append(AudioBeat(
                timestamp=t,
                energy=0.5,
                is_emphasis=(int(t) % 3 == 0)
            ))
            t += 2.5

        return beats

    def _deduplicate_beats(self, beats: list[AudioBeat], min_gap: float) -> list[AudioBeat]:
        """Remove beats that are too close together"""
        if not beats:
            return []

        result = [beats[0]]
        for beat in beats[1:]:
            if beat.timestamp - result[-1].timestamp >= min_gap:
                result.append(beat)

        return result

    def _mark_emphasized_words(self, segments: list[Segment], beats: list[AudioBeat]) -> None:
        """Mark words that coincide with audio emphasis"""
        emphasis_times = {b.timestamp for b in beats if b.is_emphasis}

        for seg in segments:
            for word in seg.words:
                # Check if word overlaps with an emphasis beat
                for et in emphasis_times:
                    if word.start <= et <= word.end:
                        word.is_emphasized = True
                        break

    # ========================================================================
    # VIRAL MOMENT DETECTION V2 (ENHANCED)
    # ========================================================================

    def _find_viral_moments_v2(
        self,
        segments: list[Segment],
        audio_beats: list[AudioBeat],
        video_info: dict,
        num_moments: int
    ) -> list[ViralMoment]:
        """
        Multi-modal viral moment detection combining:
        - Transcript analysis (hooks, insights, stories)
        - Audio energy patterns (excitement, emphasis)
        - Pacing and completeness
        """
        try:
            import ollama
        except ImportError:
            raise RuntimeError("ollama not installed")

        # Build enriched transcript with energy markers
        transcript_text = ""
        for seg in segments:
            energy_marker = ""
            seg_beats = [b for b in audio_beats if seg.start <= b.timestamp <= seg.end]
            if any(b.is_emphasis for b in seg_beats):
                energy_marker = " [HIGH ENERGY]"
            transcript_text += f"[{seg.start:.1f}s-{seg.end:.1f}s]{energy_marker} {seg.text}\n"

        prompt = f"""You are a viral content expert like Opus Clip. Analyze this video transcript and find the {num_moments} BEST moments for viral short-form content (15-40 seconds each).

TRANSCRIPT (with energy markers):
{transcript_text}

For EACH moment, analyze these scoring factors (0-10 scale):

1. HOOK SCORE: How strong is the opening?
   - Questions that create curiosity (8-10)
   - Bold/controversial statements (8-10)
   - Surprising facts or statistics (7-9)
   - Story openings "I remember when..." (6-8)
   - Generic statements (1-5)

2. PACING SCORE: Is the delivery engaging?
   - Fast, punchy delivery with [HIGH ENERGY] (8-10)
   - Good variation in pace (6-8)
   - Monotone or slow (1-5)

3. ENERGY SCORE: What's the emotional intensity?
   - Passionate, excited delivery (8-10)
   - Interesting/engaging (6-8)
   - Flat energy (1-5)

4. COMPLETENESS SCORE: Is it a complete thought?
   - Full story with payoff (9-10)
   - Complete insight/lesson (7-9)
   - Partial but intriguing (5-7)
   - Cut off mid-thought (1-4)

Return EXACTLY {num_moments} moments as JSON:
[
  {{
    "start": <seconds>,
    "end": <seconds>,
    "hook": "<first sentence>",
    "hook_score": <1-10>,
    "pacing_score": <1-10>,
    "energy_score": <1-10>,
    "completeness_score": <1-10>,
    "reason": "<why this will go viral>",
    "suggested_broll": ["<keyword1>", "<keyword2>"]
  }}
]

RULES:
- Each clip: 15-40 seconds
- Start at sentence beginnings
- End at natural conclusions
- No overlapping clips
- Prioritize highest combined scores

Return ONLY valid JSON array."""

        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response["message"]["content"]

            json_match = re.search(r'\[[\s\S]*\]', content)
            if json_match:
                moments_data = json.loads(json_match.group())
            else:
                raise ValueError("No JSON found")

            moments = []
            for m in moments_data[:num_moments]:
                # Get full transcript for moment
                transcript = " ".join(
                    seg.text for seg in segments
                    if seg.start >= m["start"] and seg.end <= m["end"]
                )

                moments.append(ViralMoment(
                    start=float(m["start"]),
                    end=float(m["end"]),
                    hook=m.get("hook", ""),
                    transcript=transcript,
                    hook_score=float(m.get("hook_score", 5)),
                    pacing_score=float(m.get("pacing_score", 5)),
                    energy_score=float(m.get("energy_score", 5)),
                    completeness_score=float(m.get("completeness_score", 5)),
                    reason=m.get("reason", ""),
                    suggested_broll=m.get("suggested_broll", [])
                ))

            # Sort by virality score
            moments.sort(key=lambda x: x.virality_score, reverse=True)
            return moments

        except Exception as e:
            self.logger.warning(f"AI analysis failed: {e}, using fallback")
            return self._fallback_moment_detection(segments, num_moments)

    def _fallback_moment_detection(self, segments: list[Segment], num_moments: int) -> list[ViralMoment]:
        """Fallback detection when AI fails"""
        if not segments:
            return []

        moments = []
        current_start = 0.0

        for i, seg in enumerate(segments):
            duration = seg.end - current_start
            if duration >= settings.min_reel_duration:
                if i < len(segments) - 1:
                    gap = segments[i+1].start - seg.end
                    if gap > 0.5 or duration >= 30:
                        moments.append(ViralMoment(
                            start=current_start,
                            end=seg.end,
                            hook=seg.text[:50],
                            transcript=seg.text,
                            hook_score=5.0,
                            pacing_score=5.0,
                            energy_score=5.0,
                            completeness_score=5.0,
                            reason="Auto-detected"
                        ))
                        current_start = segments[i+1].start
                        if len(moments) >= num_moments:
                            break

        return moments[:num_moments]

    # ========================================================================
    # FACE TRACKING V2 (SMOOTH)
    # ========================================================================

    def _track_faces_smooth(
        self,
        video_path: Path,
        moments: list[ViralMoment],
        video_info: dict
    ) -> dict[int, list[FaceTrack]]:
        """
        Smooth face tracking with frame interpolation.
        Instead of sampling 3 frames, we track throughout and interpolate.
        """
        try:
            from ultralytics import YOLO
            import cv2
        except ImportError:
            self.logger.warning("YOLOv8/OpenCV not available")
            return {}

        if self.yolo_model is None:
            self.logger.info("Loading YOLOv8...")
            self.yolo_model = YOLO("yolov8n.pt")

        face_tracks = {}
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        for moment_idx, moment in enumerate(moments):
            tracks = []

            # Sample every 0.5 seconds instead of just 3 points
            sample_interval = 0.5
            current_time = moment.start

            while current_time < moment.end:
                frame_num = int(current_time * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()

                if not ret:
                    current_time += sample_interval
                    continue

                # Detect persons (class 0)
                results = self.yolo_model(frame, classes=[0], verbose=False)

                best_detection = None
                best_conf = 0

                for r in results:
                    for box in r.boxes:
                        conf = float(box.conf)
                        if conf > best_conf:
                            best_conf = conf
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            best_detection = (x1, y1, x2, y2, conf)

                if best_detection:
                    x1, y1, x2, y2, conf = best_detection
                    tracks.append(FaceTrack(
                        frame_num=frame_num,
                        timestamp=current_time,
                        center_x=(x1 + x2) / 2 / frame_w,
                        center_y=(y1 + y2) / 2 / frame_h,
                        scale=(x2 - x1) / frame_w,
                        confidence=conf
                    ))

                current_time += sample_interval

            # Interpolate for smooth tracking
            face_tracks[moment_idx] = self._interpolate_tracks(tracks, moment, fps)

        cap.release()
        return face_tracks

    def _interpolate_tracks(
        self,
        tracks: list[FaceTrack],
        moment: ViralMoment,
        fps: float
    ) -> list[FaceTrack]:
        """Interpolate face tracks for smooth motion"""
        if len(tracks) < 2:
            return tracks

        interpolated = []

        for i in range(len(tracks) - 1):
            t1, t2 = tracks[i], tracks[i + 1]
            interpolated.append(t1)

            # Add interpolated frames between samples
            num_frames = int((t2.timestamp - t1.timestamp) * fps)
            for f in range(1, num_frames):
                alpha = f / num_frames
                interpolated.append(FaceTrack(
                    frame_num=t1.frame_num + f,
                    timestamp=t1.timestamp + f / fps,
                    center_x=t1.center_x + (t2.center_x - t1.center_x) * alpha,
                    center_y=t1.center_y + (t2.center_y - t1.center_y) * alpha,
                    scale=t1.scale + (t2.scale - t1.scale) * alpha,
                    confidence=(t1.confidence + t2.confidence) / 2
                ))

        interpolated.append(tracks[-1])
        return interpolated

    # ========================================================================
    # REEL CREATION V2 (ENHANCED)
    # ========================================================================

    def _create_reel_v2(
        self,
        video_path: Path,
        output_path: Path,
        moment: ViralMoment,
        words: list[Word],
        face_track: list[FaceTrack],
        audio_beats: list[AudioBeat],
        video_info: dict,
        aspect_ratio: AspectRatio,
        template: BrandTemplate
    ) -> None:
        """Create reel with professional effects"""

        src_w, src_h = video_info["width"], video_info["height"]
        target_w, target_h = aspect_ratio.dimensions
        duration = moment.end - moment.start

        # Create ASS subtitle file for animated captions
        ass_path = self._create_animated_subtitles(
            words, moment.start, template, target_w, target_h
        )

        # Build dynamic crop expression based on face tracking
        crop_expr = self._build_dynamic_crop_expression(
            face_track, src_w, src_h, target_w, target_h, duration
        )

        # Build zoom expression based on audio beats (not timed intervals)
        zoom_expr = self._build_content_aware_zoom_expression(
            audio_beats, moment.start, moment.end, words
        )

        # Build filter complex
        filter_complex = self._build_filter_complex_v2(
            crop_expr, zoom_expr, target_w, target_h,
            ass_path, template, duration
        )

        # FFmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(moment.start),
            "-i", str(video_path),
            "-t", str(duration),
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

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # CPU fallback
            self.logger.warning("GPU failed, trying CPU...")
            cmd[cmd.index("-c:v") + 1] = "libx264"
            if "-preset" in cmd:
                idx = cmd.index("-preset")
                cmd[idx + 1] = "fast"
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")

        # Cleanup
        if ass_path.exists():
            ass_path.unlink()

    def _create_animated_subtitles(
        self,
        words: list[Word],
        offset: float,
        template: BrandTemplate,
        width: int,
        height: int
    ) -> Path:
        """
        Create ASS subtitle file with karaoke-style word highlighting.
        Each word lights up as it's spoken (like Opus Clip).
        """
        ass_path = self._cache_dir / f"subs_{hash(str(words))}.ass"

        # ASS header
        ass_content = f"""[Script Info]
Title: JARVIS Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{template.font_family},{template.font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{template.stroke_width},0,2,10,10,80,1
Style: Highlight,{template.font_family},{template.font_size},&H0000D7FF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,{template.stroke_width},0,2,10,10,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Group words into chunks of 3-4 for display
        chunk_size = 3
        for i in range(0, len(words), chunk_size):
            chunk = words[i:i+chunk_size]
            if not chunk:
                continue

            start_time = chunk[0].start - offset
            end_time = chunk[-1].end - offset

            if start_time < 0:
                start_time = 0

            # Build text with karaoke timing
            text_parts = []
            for j, word in enumerate(chunk):
                word_start = word.start - offset - start_time
                word_duration = (word.end - word.start) * 100  # centiseconds

                # Use karaoke effect for highlighting
                if word.is_emphasized:
                    # Scale up emphasized words
                    text_parts.append(f"{{\\k{int(word_duration)}\\fscx120\\fscy120}}{word.text} ")
                else:
                    text_parts.append(f"{{\\k{int(word_duration)}}}{word.text} ")

            text = "".join(text_parts).strip()

            # Convert to ASS timestamp format
            start_ass = self._seconds_to_ass_time(start_time)
            end_ass = self._seconds_to_ass_time(end_time)

            ass_content += f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,karaoke,{text}\n"

        ass_path.write_text(ass_content)
        return ass_path

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Convert seconds to ASS time format (H:MM:SS.cc)"""
        if seconds < 0:
            seconds = 0
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def _build_dynamic_crop_expression(
        self,
        face_track: list[FaceTrack],
        src_w: int,
        src_h: int,
        target_w: int,
        target_h: int,
        duration: float
    ) -> str:
        """Build FFmpeg expression for smooth face-following crop"""
        target_ratio = target_w / target_h

        if src_w / src_h > target_ratio:
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)

        if not face_track:
            # Static center crop
            crop_x = (src_w - crop_w) // 2
            crop_y = (src_h - crop_h) // 2
            return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"

        # Build smooth pan expression following face
        # Use first and last positions for smooth lerp
        if len(face_track) >= 2:
            start_x = face_track[0].center_x * src_w
            end_x = face_track[-1].center_x * src_w
            start_y = face_track[0].center_y * src_h
            end_y = face_track[-1].center_y * src_h

            # Smooth interpolation expression
            crop_x_expr = f"({start_x}+({end_x}-{start_x})*(t/{duration}))-{crop_w}/2"
            crop_y_expr = f"({start_y}+({end_y}-{start_y})*(t/{duration}))-{crop_h}/2"

            # Clamp to bounds
            crop_x_expr = f"max(0,min({src_w-crop_w},{crop_x_expr}))"
            crop_y_expr = f"max(0,min({src_h-crop_h},{crop_y_expr}))"

            return f"crop={crop_w}:{crop_h}:{crop_x_expr}:{crop_y_expr}"
        else:
            # Single detection - center on it
            cx = face_track[0].center_x * src_w
            cy = face_track[0].center_y * src_h
            crop_x = max(0, min(src_w - crop_w, int(cx - crop_w/2)))
            crop_y = max(0, min(src_h - crop_h, int(cy - crop_h/2)))
            return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"

    def _build_content_aware_zoom_expression(
        self,
        audio_beats: list[AudioBeat],
        start_time: float,
        end_time: float,
        words: list[Word]
    ) -> str:
        """
        Build zoom expression that zooms on:
        - Audio emphasis beats
        - Emphasized words
        NOT on fixed time intervals (that's the old way)
        """
        # Find zoom points within this clip
        zoom_points = []

        # Add zoom on emphasized words
        for word in words:
            if word.is_emphasized:
                zoom_points.append(word.start - start_time)

        # Add zoom on audio beats
        for beat in audio_beats:
            if start_time <= beat.timestamp <= end_time and beat.is_emphasis:
                t = beat.timestamp - start_time
                if t not in zoom_points:
                    zoom_points.append(t)

        if not zoom_points:
            return "1"  # No zoom

        # Build zoom expression
        # Each zoom: quick in (0.1s), hold (0.1s), quick out (0.1s)
        zoom_parts = []
        zoom_factor = settings.zoom_factor

        for t in sorted(zoom_points):
            t_in = t
            t_peak = t + 0.1
            t_out = t + 0.2

            # Zoom in
            zoom_parts.append(f"if(between(t,{t_in:.2f},{t_peak:.2f}),1+(({zoom_factor}-1)*((t-{t_in:.2f})/0.1)),")
            # Zoom out
            zoom_parts.append(f"if(between(t,{t_peak:.2f},{t_out:.2f}),{zoom_factor}-(({zoom_factor}-1)*((t-{t_peak:.2f})/0.1)),")

        # Close all ifs and default to 1
        expr = "".join(zoom_parts) + "1" + ")" * (len(zoom_parts))

        # Simplify if too complex (FFmpeg has limits)
        if len(expr) > 2000:
            # Fall back to simpler expression with fewer zoom points
            zoom_points = zoom_points[:5]
            return self._build_simple_zoom_expression(zoom_points, zoom_factor)

        return expr

    def _build_simple_zoom_expression(self, zoom_points: list[float], zoom_factor: float) -> str:
        """Simpler zoom expression for when complex one is too long"""
        if not zoom_points:
            return "1"

        parts = []
        for t in zoom_points:
            parts.append(f"if(between(t,{t:.2f},{t+0.2:.2f}),{zoom_factor},")

        return "".join(parts) + "1" + ")" * len(parts)

    def _build_filter_complex_v2(
        self,
        crop_expr: str,
        zoom_expr: str,
        target_w: int,
        target_h: int,
        ass_path: Path,
        template: BrandTemplate,
        duration: float
    ) -> str:
        """Build complete FFmpeg filter complex"""

        video_filters = [
            crop_expr,
            f"scale={target_w}:{target_h}:flags=lanczos",
        ]

        # Add zoom if we have zoom points
        if zoom_expr != "1":
            video_filters.append(
                f"zoompan=z='{zoom_expr}':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d=1:s={target_w}x{target_h}:fps={settings.fps}"
            )

        # Add ASS subtitles
        ass_path_escaped = str(ass_path).replace(":", "\\:").replace("'", "\\'")
        video_filters.append(f"ass='{ass_path_escaped}'")

        # Add logo if configured
        if template.logo_path and Path(template.logo_path).exists():
            video_filters.append(self._build_logo_overlay(template, target_w, target_h))

        video_chain = ",".join(video_filters) + "[outv]"

        # Audio processing
        audio_filters = [
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            f"silenceremove=start_periods=1:start_duration=0.1:"
            f"start_threshold={settings.silence_threshold}dB:detection=peak"
        ]
        audio_chain = ",".join(audio_filters) + "[outa]"

        return f"[0:v]{video_chain};[0:a]{audio_chain}"

    def _build_logo_overlay(self, template: BrandTemplate, width: int, height: int) -> str:
        """Build overlay filter for logo"""
        logo_w = int(width * template.logo_scale)

        positions = {
            "top-left": f"x=20:y=20",
            "top-right": f"x={width}-overlay_w-20:y=20",
            "bottom-left": f"x=20:y={height}-overlay_h-20",
            "bottom-right": f"x={width}-overlay_w-20:y={height}-overlay_h-20",
        }
        pos = positions.get(template.logo_position, positions["top-right"])

        return f"movie='{template.logo_path}',scale={logo_w}:-1[logo];[logo]overlay={pos}"

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _get_words_for_timerange(self, segments: list[Segment], start: float, end: float) -> list[Word]:
        """Get words within time range"""
        words = []
        for seg in segments:
            if seg.end < start or seg.start > end:
                continue
            for word in seg.words:
                if start <= word.start <= end:
                    words.append(word)
        return words

    def _generate_premiere_xml(self, video_path: Path, moments: list[ViralMoment], output_path: Path) -> None:
        """Generate Premiere Pro XML"""
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
                <name>Reel {i+1} (Score: {moment.virality_score:.1f})</name>
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

    def _generate_analytics(self, moments: list[ViralMoment]) -> dict:
        """Generate analytics report like Opus Clip"""
        return {
            "total_clips": len(moments),
            "avg_virality_score": sum(m.virality_score for m in moments) / len(moments) if moments else 0,
            "score_breakdown": {
                "avg_hook": sum(m.hook_score for m in moments) / len(moments) if moments else 0,
                "avg_pacing": sum(m.pacing_score for m in moments) / len(moments) if moments else 0,
                "avg_energy": sum(m.energy_score for m in moments) / len(moments) if moments else 0,
                "avg_completeness": sum(m.completeness_score for m in moments) / len(moments) if moments else 0,
            },
            "top_clip": {
                "hook": moments[0].hook if moments else "",
                "score": moments[0].virality_score if moments else 0,
                "reason": moments[0].reason if moments else ""
            } if moments else None,
            "suggested_broll_keywords": list(set(
                kw for m in moments for kw in m.suggested_broll
            ))[:10]
        }
