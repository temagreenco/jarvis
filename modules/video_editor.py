"""
Video Editor Module - Creates viral short-form content from long videos

Features:
- GPU-accelerated transcription (faster-whisper)
- AI analysis for viral moment detection (Ollama)
- Face/person tracking (YOLOv8)
- Multi-camera blending with auto-switching
- SRT subtitle export (separate file)
- XML project export for Premiere/DaVinci
- 9:16 vertical output
"""
import json
import subprocess
import tempfile
import random
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


@dataclass
class CameraCut:
    """A camera cut/switch point"""
    time: float
    camera: int  # 0 or 1 for two cameras
    duration: float


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
        """Validate video file(s) exist"""
        video_path = kwargs.get("video_path")
        if not video_path:
            return False, "video_path is required"

        path = Path(video_path)
        if not path.exists():
            return False, f"Video file not found: {video_path}"

        # Optional second camera
        video_path_2 = kwargs.get("video_path_2")
        if video_path_2:
            path2 = Path(video_path_2)
            if not path2.exists():
                return False, f"Second video file not found: {video_path_2}"

        return True, None

    def execute(self, task: str, **kwargs) -> TaskResult:
        """Execute video editing pipeline with multi-camera support"""
        video_path = Path(kwargs["video_path"])
        video_path_2 = kwargs.get("video_path_2")  # Optional second camera
        if video_path_2:
            video_path_2 = Path(video_path_2)
        output_dir = Path(kwargs.get("output_dir", settings.output_dir))
        num_reels = kwargs.get("num_reels", settings.target_reels)

        output_dir.mkdir(parents=True, exist_ok=True)

        multi_cam = video_path_2 is not None
        self.logger.info(f"Processing video: {video_path.name}")
        if multi_cam:
            self.logger.info(f"Second camera: {video_path_2.name}")
        self.logger.info(f"Target reels: {num_reels}")

        try:
            # Step 1: Get video info
            self.logger.info("[1/7] Analyzing video...")
            video_info = self._get_video_info(video_path)
            video_info_2 = None  # Initialize for single camera mode
            self.logger.info(f"Duration: {video_info['duration']:.1f}s, Resolution: {video_info['width']}x{video_info['height']}")

            if multi_cam:
                video_info_2 = self._get_video_info(video_path_2)
                self.logger.info(f"Camera 2: {video_info_2['width']}x{video_info_2['height']}")

            # Step 2: Transcribe with word-level timestamps
            self.logger.info("[2/7] Transcribing audio (GPU)...")
            segments = self._transcribe(video_path)
            self.logger.info(f"Transcribed {len(segments)} segments")

            # Step 3: Find viral moments with AI (improved hook detection)
            self.logger.info("[3/7] Finding viral moments (AI)...")
            moments = self._find_viral_moments(segments, num_reels)
            self.logger.info(f"Found {len(moments)} viral moments")

            # Step 4: Detect faces for smart cropping
            self.logger.info("[4/7] Detecting faces for smart crop...")
            face_data = self._detect_faces(video_path, moments)
            face_data_2 = {}
            if multi_cam:
                face_data_2 = self._detect_faces(video_path_2, moments)

            # Step 5: Generate camera cuts (2.5-5 sec intervals)
            self.logger.info("[5/7] Planning camera cuts...")
            camera_cuts = {}
            if multi_cam:
                for i, moment in enumerate(moments):
                    camera_cuts[i] = self._generate_camera_cuts(moment.start, moment.end)
                    self.logger.debug(f"Moment {i}: {len(camera_cuts[i])} camera cuts")

            # Step 6: Generate reels with SRT files
            self.logger.info("[6/7] Generating reels...")
            reel_paths = []
            srt_paths = []
            for i, moment in enumerate(moments):
                self.logger.info(f"Creating reel {i+1}/{len(moments)}: {moment.hook[:50]}...")
                reel_path = output_dir / f"reel_{i+1:02d}.mp4"
                srt_path = output_dir / f"reel_{i+1:02d}.srt"

                words_for_moment = self._get_words_for_timerange(segments, moment.start, moment.end)

                # Export SRT (separate file)
                self._export_srt(words_for_moment, moment.start, srt_path)
                srt_paths.append(srt_path)

                # Create reel (no burned subs)
                self._create_reel_multicam(
                    video_path=video_path,
                    video_path_2=video_path_2,
                    output_path=reel_path,
                    moment=moment,
                    words=words_for_moment,
                    face_data=face_data.get(i, []),
                    face_data_2=face_data_2.get(i, []),
                    video_info=video_info,
                    video_info_2=video_info_2 if multi_cam else None,
                    camera_cuts=camera_cuts.get(i, [])
                )
                reel_paths.append(reel_path)

            # Step 7: Generate project XML
            self.logger.info("[7/7] Generating project XML...")
            xml_path = output_dir / "project.xml"
            self._generate_project_xml(video_path, video_path_2, moments, camera_cuts, xml_path)

            return TaskResult(
                success=True,
                data={
                    "reels": [str(p) for p in reel_paths],
                    "subtitles": [str(p) for p in srt_paths],
                    "xml_project": str(xml_path),
                    "moments": [
                        {"start": m.start, "end": m.end, "hook": m.hook, "score": m.score}
                        for m in moments
                    ]
                },
                metadata={"video": str(video_path), "num_reels": len(reel_paths), "multi_cam": multi_cam}
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

        prompt = f"""You are a viral content expert specialized in finding HOOKS for short-form video.

TRANSCRIPT:
{transcript_text}

Find the {num_moments} BEST viral moments. Focus on PRECISE HOOK DETECTION:

HOOK PATTERNS TO FIND:
1. "Here's the thing..." / "The truth is..." / "Nobody tells you..."
2. Controversial statements / Hot takes
3. "I made $X doing..." / Results/transformations
4. Questions that create curiosity gaps
5. "Stop doing X" / "You're doing X wrong"
6. Story openings: "So there I was..." / "One day..."
7. Numbers/statistics that shock
8. "The secret to..." / "The #1 reason..."

CUTTING RULES:
- START exactly on the hook word (not before)
- END on a complete thought (punchline, conclusion, call-to-action)
- Each clip: 15-40 seconds
- No overlapping clips

Return EXACTLY {num_moments} moments as JSON:
[
  {{
    "start": <PRECISE start_seconds of hook>,
    "end": <end_seconds>,
    "score": <1-10 viral potential>,
    "reason": "<viral factor>",
    "hook": "<exact opening 3-8 words>"
  }}
]

CRITICAL: Start times must be PRECISE - the first frame should be the hook.
Return ONLY the JSON array."""

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
        """Detect faces in video for smart cropping using OpenCV + YOLO fallback"""
        try:
            import cv2
        except ImportError:
            self.logger.warning("OpenCV not available, using center crop")
            return {}

        # Load OpenCV face detector (Haar cascade - built-in, reliable)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

        face_data = {}
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)

        for i, moment in enumerate(moments):
            detections = []
            # Sample more frames for better face detection
            num_samples = 5
            duration = moment.end - moment.start
            sample_times = [moment.start + (duration * j / (num_samples - 1)) for j in range(num_samples)]

            for t in sample_times:
                frame_num = int(t * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Convert to grayscale for face detection
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Detect faces using Haar cascade
                faces = face_cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(50, 50)
                )

                for (x, y, w, h) in faces:
                    detections.append(FaceDetection(
                        frame_num=frame_num,
                        x=x,
                        y=y,
                        width=w,
                        height=h,
                        confidence=0.9  # Haar gives good confidence
                    ))

                # If no faces found, try YOLO for person detection as fallback
                if len(faces) == 0 and self.yolo_model is None:
                    try:
                        from ultralytics import YOLO
                        self.yolo_model = YOLO("yolov8n.pt")
                    except ImportError:
                        pass

                if len(faces) == 0 and self.yolo_model is not None:
                    results = self.yolo_model(frame, classes=[0], verbose=False)
                    for r in results:
                        for box in r.boxes:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            # Estimate face as top 25% of person box
                            person_h = y2 - y1
                            face_h = int(person_h * 0.25)
                            detections.append(FaceDetection(
                                frame_num=frame_num,
                                x=x1,
                                y=y1,  # Top of person = approximate face area
                                width=x2 - x1,
                                height=face_h,
                                confidence=float(box.conf) * 0.7  # Lower confidence for estimate
                            ))

            face_data[i] = detections
            self.logger.debug(f"Moment {i}: detected {len(detections)} faces")

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

    def _export_srt(self, words: list[Word], offset: float, output_path: Path) -> None:
        """Export subtitles to SRT file (not burned in)"""
        chunk_size = settings.subtitle_words_per_chunk
        srt_content = []
        sub_index = 1

        for i in range(0, len(words), chunk_size):
            chunk = words[i:i+chunk_size]
            if not chunk:
                continue

            text = " ".join(w.text for w in chunk)
            text = self._clean_subtitle_text(text)
            if not text:
                continue

            # Calculate timing relative to clip start
            start = chunk[0].start - offset
            end = chunk[-1].end - offset
            start = max(0, start)

            # Format as SRT timestamp: HH:MM:SS,mmm
            def format_time(seconds: float) -> str:
                h = int(seconds // 3600)
                m = int((seconds % 3600) // 60)
                s = int(seconds % 60)
                ms = int((seconds % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            srt_content.append(f"{sub_index}")
            srt_content.append(f"{format_time(start)} --> {format_time(end)}")
            srt_content.append(text)
            srt_content.append("")
            sub_index += 1

        output_path.write_text("\n".join(srt_content), encoding="utf-8")
        self.logger.debug(f"Exported SRT: {output_path} ({sub_index - 1} subtitles)")

    def _generate_camera_cuts(self, start: float, end: float) -> list[CameraCut]:
        """Generate camera switching points every 2.5-5 seconds"""
        cuts = []
        current_time = 0.0
        duration = end - start
        current_camera = 0

        while current_time < duration:
            # Random cut duration between 2.5-5 seconds
            cut_duration = random.uniform(2.5, 5.0)

            # Don't exceed clip duration
            if current_time + cut_duration > duration:
                cut_duration = duration - current_time

            if cut_duration > 0.5:  # Only add if meaningful duration
                cuts.append(CameraCut(
                    time=current_time,
                    camera=current_camera,
                    duration=cut_duration
                ))

            current_time += cut_duration
            current_camera = 1 - current_camera  # Alternate cameras

        return cuts

    def _create_reel_multicam(
        self,
        video_path: Path,
        video_path_2: Optional[Path],
        output_path: Path,
        moment: ViralMoment,
        words: list[Word],
        face_data: list[FaceDetection],
        face_data_2: list[FaceDetection],
        video_info: dict,
        video_info_2: Optional[dict],
        camera_cuts: list[CameraCut]
    ) -> None:
        """Create a reel with multi-camera switching (no burned subtitles)"""

        src_w, src_h = video_info["width"], video_info["height"]
        target_w, target_h = settings.output_width, settings.output_height
        target_ratio = target_w / target_h
        duration = moment.end - moment.start

        # Calculate crop for camera 1
        crop1 = self._calculate_crop(face_data, src_w, src_h, target_ratio)

        # Calculate crop for camera 2 (if multi-cam)
        crop2 = crop1  # Default to same crop
        if video_path_2 and video_info_2:
            src_w2, src_h2 = video_info_2["width"], video_info_2["height"]
            crop2 = self._calculate_crop(face_data_2, src_w2, src_h2, target_ratio)

        # Build filter complex
        if video_path_2 and camera_cuts:
            # Multi-camera with cuts
            filter_complex = self._build_multicam_filter(
                crop1, crop2, target_w, target_h, camera_cuts, duration
            )
            # Two input files
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(moment.start), "-i", str(video_path),
                "-ss", str(moment.start), "-i", str(video_path_2),
                "-t", str(duration),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
            ]
        else:
            # Single camera
            filter_complex = self._build_single_cam_filter(
                crop1, target_w, target_h, duration
            )
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(moment.start), "-i", str(video_path),
                "-t", str(duration),
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
            ]

        # Add encoding options
        cmd.extend([
            "-c:v", settings.video_codec,
            "-preset", settings.ffmpeg_preset,
            "-crf", str(settings.ffmpeg_crf),
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-c:a", settings.audio_codec,
            "-b:a", settings.audio_bitrate,
            "-movflags", "+faststart",
            str(output_path)
        ])

        self.logger.debug(f"Running FFmpeg: {' '.join(cmd[:20])}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            # Fallback to CPU encoding
            self.logger.warning(f"GPU encoding failed, trying CPU...")
            cmd = [c if c != settings.video_codec else "libx264" for c in cmd]
            cmd = [c if c != settings.ffmpeg_preset else "fast" for c in cmd]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr[:500]}")

    def _calculate_crop(
        self,
        face_data: list[FaceDetection],
        src_w: int, src_h: int,
        target_ratio: float
    ) -> tuple[int, int, int, int]:
        """Calculate crop region based on face detection"""
        # Calculate crop dimensions
        if src_w / src_h > target_ratio:
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)

        if face_data:
            strong_detections = [f for f in face_data if f.confidence > 0.5] or face_data
            total_conf = sum(f.confidence for f in strong_detections)
            if total_conf > 0:
                face_center_x = sum((f.x + f.width/2) * f.confidence for f in strong_detections) / total_conf
                face_center_y = sum((f.y + f.height/2) * f.confidence for f in strong_detections) / total_conf
            else:
                face_center_x = sum(f.x + f.width/2 for f in strong_detections) / len(strong_detections)
                face_center_y = sum(f.y + f.height/2 for f in strong_detections) / len(strong_detections)

            center_x = int(face_center_x)
            face_target_y = face_center_y
        else:
            center_x = src_w // 2
            face_target_y = src_h // 3

        # Position crop
        desired_crop_y = int(face_target_y - crop_h / 3)
        crop_y = max(0, min(desired_crop_y, src_h - crop_h))
        desired_crop_x = int(center_x - crop_w // 2)
        crop_x = max(0, min(desired_crop_x, src_w - crop_w))

        return crop_x, crop_y, crop_w, crop_h

    def _build_multicam_filter(
        self,
        crop1: tuple, crop2: tuple,
        target_w: int, target_h: int,
        camera_cuts: list[CameraCut],
        duration: float
    ) -> str:
        """Build FFmpeg filter for multi-camera switching"""
        cx1, cy1, cw1, ch1 = crop1
        cx2, cy2, cw2, ch2 = crop2

        # Process both cameras
        filters = []
        filters.append(f"[0:v]crop={cw1}:{ch1}:{cx1}:{cy1},scale={target_w}:{target_h}:flags=lanczos,fps={settings.fps}[cam0]")
        filters.append(f"[1:v]crop={cw2}:{ch2}:{cx2}:{cy2},scale={target_w}:{target_h}:flags=lanczos,fps={settings.fps}[cam1]")

        # Build camera switch timeline using overlay with enable
        # Start with cam0 as base
        switch_expr_parts = []
        for cut in camera_cuts:
            t_start = cut.time
            t_end = cut.time + cut.duration
            if cut.camera == 1:
                switch_expr_parts.append(f"between(t,{t_start:.3f},{t_end:.3f})")

        if switch_expr_parts:
            # Overlay cam1 on cam0 when cam1 is active
            switch_expr = "+".join(switch_expr_parts)
            filters.append(f"[cam0][cam1]overlay=enable='{switch_expr}'[vmix]")
        else:
            filters.append("[cam0]copy[vmix]")

        # Add visual enhancements
        filters.append("[vmix]eq=contrast=1.08:saturation=1.10,unsharp=5:5:0.8:5:5:0.4[outv]")

        # Audio from first source
        filters.append("[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[outa]")

        return ";".join(filters)

    def _build_single_cam_filter(
        self,
        crop: tuple,
        target_w: int, target_h: int,
        duration: float
    ) -> str:
        """Build FFmpeg filter for single camera (no burned subtitles)"""
        cx, cy, cw, ch = crop

        video_chain = (
            f"crop={cw}:{ch}:{cx}:{cy},"
            f"scale={target_w}:{target_h}:flags=lanczos,"
            f"fps={settings.fps},"
            "eq=contrast=1.08:saturation=1.10,"
            "unsharp=5:5:0.8:5:5:0.4"
        )

        return f"[0:v]{video_chain}[outv];[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[outa]"

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

            # Use weighted average by confidence for FACE center
            total_conf = sum(f.confidence for f in strong_detections)
            if total_conf > 0:
                # Face center X
                face_center_x = sum((f.x + f.width/2) * f.confidence for f in strong_detections) / total_conf
                # Face center Y (center of face box, not top)
                face_center_y = sum((f.y + f.height/2) * f.confidence for f in strong_detections) / total_conf
            else:
                face_center_x = sum(f.x + f.width/2 for f in strong_detections) / len(strong_detections)
                face_center_y = sum(f.y + f.height/2 for f in strong_detections) / len(strong_detections)

            center_x = int(face_center_x)
            # Face center should appear at upper 1/3 of output (closer to top)
            face_target_y = face_center_y

            # Safety: ensure center_x is not too close to edges
            min_margin_x = src_w * 0.15  # 15% margin from edges
            center_x = int(max(min_margin_x, min(center_x, src_w - min_margin_x)))

            self.logger.info(f"Face detected: center=({center_x}, {face_target_y:.0f}), {len(strong_detections)} detections")
        else:
            # No detection - use center of frame
            center_x = src_w // 2
            face_target_y = src_h // 3  # Default to upper third
            self.logger.info("No face detected, using center crop")

        # Calculate crop dimensions to get 9:16
        if src_w / src_h > target_ratio:
            # Video is wider - crop width
            crop_h = src_h
            crop_w = int(crop_h * target_ratio)
        else:
            # Video is taller - crop height
            crop_w = src_w
            crop_h = int(crop_w / target_ratio)

        # Position crop so FACE CENTER is at upper 1/3 of output frame
        # Upper 1/3 line is at crop_h / 3 from top
        # We want face_target_y (in source) to appear at crop_h/3 (in output)
        # So: crop_y + crop_h/3 = face_target_y  =>  crop_y = face_target_y - crop_h/3
        desired_crop_y = int(face_target_y - crop_h / 3)
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
        """Create drawtext filter for word-synced subtitles - Opus Clip style

        Key features (like pro tools):
        1. Seamless transitions - each subtitle ends when next starts
        2. No gaps - continuous subtitle display during speech
        3. Minimum display time - prevents flashing
        4. Small transition overlap - no blank frames
        """
        if not words:
            return ""

        chunk_size = settings.subtitle_words_per_chunk
        font_path = self._find_font()
        sub_offset = getattr(settings, 'subtitle_offset', 0)
        min_display_time = 0.4  # Minimum time to show each subtitle
        transition_overlap = 0.05  # Small overlap to prevent blank frames

        # Bolder settings
        font_size = settings.subtitle_font_size + 10
        stroke_width = settings.subtitle_stroke_width + 2

        # Build chunks first
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i+chunk_size]
            text = " ".join(w.text for w in chunk_words)
            text = self._clean_subtitle_text(text)
            if not text:
                continue

            # Escape for FFmpeg
            text = text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "\\%")

            chunks.append({
                'text': text,
                'start': chunk_words[0].start,
                'end': chunk_words[-1].end
            })

        if not chunks:
            return ""

        # Calculate seamless timings (each ends when next starts)
        filters = []
        for i, chunk in enumerate(chunks):
            # Start time with offset
            start = chunk['start'] - offset + sub_offset

            # End time: when next chunk starts (seamless) or word end + buffer for last
            if i < len(chunks) - 1:
                # End when next subtitle starts (+ small overlap for smooth transition)
                next_start = chunks[i + 1]['start'] - offset + sub_offset
                end = next_start + transition_overlap
            else:
                # Last subtitle: use word end time + buffer
                end = chunk['end'] - offset + sub_offset + 0.3

            # Ensure minimum display time
            if end - start < min_display_time:
                end = start + min_display_time

            # Ensure start isn't negative
            start = max(0, start)

            # Font clause
            if font_path:
                font_clause = f"fontfile='{font_path}':"
            else:
                font_clause = f"font='{settings.subtitle_font}':"

            pos_y = getattr(settings, 'subtitle_position_y', 0.82)
            filters.append(
                f"drawtext=text='{chunk['text']}':"
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

        # Audio processing: loudness normalization only
        # Note: silenceremove disabled because it breaks subtitle sync
        # (audio duration changes but subtitle timings stay fixed)
        audio_filters = [
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

    def _generate_project_xml(
        self,
        video_path: Path,
        video_path_2: Optional[Path],
        moments: list[ViralMoment],
        camera_cuts: dict[int, list[CameraCut]],
        output_path: Path
    ) -> None:
        """Generate detailed project XML with multi-cam and markers"""
        fps = settings.fps
        video_url = str(video_path.absolute()).replace("\\", "/")
        video_url_2 = str(video_path_2.absolute()).replace("\\", "/") if video_path_2 else None

        # Build comprehensive XML
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE xmeml>',
            '<xmeml version="5">',
            '  <project>',
            '    <name>JARVIS Multi-Cam Project</name>',
            '    <children>',
        ]

        # Add bin for source clips
        xml_lines.extend([
            '      <bin>',
            '        <name>Source Media</name>',
            '        <children>',
            f'          <clip id="masterclip-1">',
            f'            <name>Camera 1</name>',
            f'            <pathurl>file:///{video_url}</pathurl>',
            f'          </clip>',
        ])
        if video_url_2:
            xml_lines.extend([
                f'          <clip id="masterclip-2">',
                f'            <name>Camera 2</name>',
                f'            <pathurl>file:///{video_url_2}</pathurl>',
                f'          </clip>',
            ])
        xml_lines.extend([
            '        </children>',
            '      </bin>',
        ])

        # Main sequence with all clips
        xml_lines.extend([
            '      <sequence>',
            '        <name>Reels Timeline</name>',
            f'        <rate><timebase>{fps}</timebase></rate>',
            '        <media>',
            '          <video>',
            '            <track>',
        ])

        timeline_pos = 0
        for i, moment in enumerate(moments):
            duration_frames = int((moment.end - moment.start) * fps)
            in_frame = int(moment.start * fps)
            out_frame = int(moment.end * fps)

            # Add main clip
            xml_lines.extend([
                f'              <clipitem id="reel{i+1}">',
                f'                <name>Reel {i+1}: {moment.hook[:30]}</name>',
                f'                <start>{timeline_pos}</start>',
                f'                <end>{timeline_pos + duration_frames}</end>',
                f'                <in>{in_frame}</in>',
                f'                <out>{out_frame}</out>',
                f'                <file id="file-1">',
                f'                  <pathurl>file:///{video_url}</pathurl>',
                f'                </file>',
            ])

            # Add markers for camera cuts
            if i in camera_cuts:
                xml_lines.append('                <marker>')
                for cut in camera_cuts[i]:
                    cut_frame = int(cut.time * fps)
                    xml_lines.extend([
                        f'                  <comment>CAM{cut.camera + 1} @ {cut.time:.1f}s</comment>',
                        f'                  <in>{cut_frame}</in>',
                        f'                  <out>{cut_frame + 1}</out>',
                    ])
                xml_lines.append('                </marker>')

            xml_lines.append('              </clipitem>')

            # Add gap between clips
            xml_lines.extend([
                f'              <transitionitem>',
                f'                <start>{timeline_pos + duration_frames}</start>',
                f'                <end>{timeline_pos + duration_frames + fps}</end>',
                f'              </transitionitem>',
            ])
            timeline_pos += duration_frames + fps  # 1 second gap

        xml_lines.extend([
            '            </track>',
        ])

        # Second video track for cam2 if multi-cam
        if video_url_2 and camera_cuts:
            xml_lines.extend([
                '            <track>',
                '              <!-- Camera 2 clips for multicam editing -->',
            ])
            timeline_pos = 0
            for i, moment in enumerate(moments):
                duration_frames = int((moment.end - moment.start) * fps)
                in_frame = int(moment.start * fps)

                if i in camera_cuts:
                    for cut in camera_cuts[i]:
                        if cut.camera == 1:  # Camera 2
                            cut_start = int(cut.time * fps)
                            cut_end = int((cut.time + cut.duration) * fps)
                            xml_lines.extend([
                                f'              <clipitem>',
                                f'                <name>Cam2 Cut</name>',
                                f'                <start>{timeline_pos + cut_start}</start>',
                                f'                <end>{timeline_pos + cut_end}</end>',
                                f'                <in>{in_frame + cut_start}</in>',
                                f'                <out>{in_frame + cut_end}</out>',
                                f'                <file id="file-2">',
                                f'                  <pathurl>file:///{video_url_2}</pathurl>',
                                f'                </file>',
                                f'              </clipitem>',
                            ])
                timeline_pos += duration_frames + fps

            xml_lines.append('            </track>')

        xml_lines.extend([
            '          </video>',
            '          <audio>',
            '            <track>',
            '              <!-- Audio from Camera 1 -->',
            '            </track>',
            '          </audio>',
            '        </media>',
            '      </sequence>',
        ])

        # Add markers bin for viral moments
        xml_lines.extend([
            '      <bin>',
            '        <name>Viral Moments</name>',
            '        <children>',
        ])
        for i, moment in enumerate(moments):
            xml_lines.extend([
                f'          <marker>',
                f'            <name>Reel {i+1}</name>',
                f'            <comment>Score: {moment.score}/10 - {moment.reason[:50]}</comment>',
                f'            <in>{int(moment.start * fps)}</in>',
                f'            <out>{int(moment.end * fps)}</out>',
                f'          </marker>',
            ])
        xml_lines.extend([
            '        </children>',
            '      </bin>',
            '    </children>',
            '  </project>',
            '</xmeml>',
        ])

        output_path.write_text("\n".join(xml_lines), encoding="utf-8")
        self.logger.info(f"Project XML saved: {output_path}")
