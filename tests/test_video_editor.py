"""Tests for VideoEditorModule"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile

from modules.video_editor import (
    VideoEditorModule,
    Word,
    Segment,
    ViralMoment,
    FaceDetection
)


class TestWord:
    """Tests for Word dataclass"""

    def test_word_creation(self):
        word = Word(text="hello", start=0.0, end=0.5)
        assert word.text == "hello"
        assert word.start == 0.0
        assert word.end == 0.5
        assert word.confidence == 1.0

    def test_word_with_confidence(self):
        word = Word(text="world", start=1.0, end=1.5, confidence=0.95)
        assert word.confidence == 0.95


class TestSegment:
    """Tests for Segment dataclass"""

    def test_segment_creation(self):
        seg = Segment(text="Hello world", start=0.0, end=2.0)
        assert seg.text == "Hello world"
        assert seg.start == 0.0
        assert seg.end == 2.0
        assert seg.words == []

    def test_segment_with_words(self):
        words = [
            Word(text="Hello", start=0.0, end=0.5),
            Word(text="world", start=0.5, end=1.0)
        ]
        seg = Segment(text="Hello world", start=0.0, end=1.0, words=words)
        assert len(seg.words) == 2


class TestViralMoment:
    """Tests for ViralMoment dataclass"""

    def test_viral_moment_creation(self):
        moment = ViralMoment(
            start=10.0,
            end=40.0,
            score=8.5,
            reason="Strong hook",
            hook="You won't believe this"
        )
        assert moment.start == 10.0
        assert moment.end == 40.0
        assert moment.score == 8.5
        assert moment.reason == "Strong hook"
        assert moment.hook == "You won't believe this"


class TestFaceDetection:
    """Tests for FaceDetection dataclass"""

    def test_face_detection_creation(self):
        face = FaceDetection(
            frame_num=100,
            x=200,
            y=150,
            width=100,
            height=120,
            confidence=0.92
        )
        assert face.frame_num == 100
        assert face.x == 200
        assert face.confidence == 0.92


class TestVideoEditorModule:
    """Tests for VideoEditorModule"""

    def test_module_properties(self):
        module = VideoEditorModule()
        assert module.name == "video_editor"
        assert module.version == "0.1.0"

    def test_can_handle(self):
        module = VideoEditorModule()
        assert module.can_handle("edit this video") is True
        assert module.can_handle("create a reel") is True
        assert module.can_handle("make youtube shorts") is True
        assert module.can_handle("cut the clip") is True
        assert module.can_handle("transcribe audio") is True
        assert module.can_handle("chat with me") is False
        assert module.can_handle("send email") is False

    def test_validate_inputs_missing_path(self):
        module = VideoEditorModule()
        valid, error = module.validate_inputs()
        assert valid is False
        assert "video_path is required" in error

    def test_validate_inputs_file_not_found(self):
        module = VideoEditorModule()
        valid, error = module.validate_inputs(video_path="/nonexistent/video.mp4")
        assert valid is False
        assert "not found" in error

    def test_validate_inputs_valid_file(self):
        module = VideoEditorModule()
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            valid, error = module.validate_inputs(video_path=f.name)
            assert valid is True
            assert error is None

    def test_is_available(self):
        module = VideoEditorModule()
        available, msg = module.is_available()
        # Result depends on whether ffmpeg is installed
        assert isinstance(available, bool)
        assert isinstance(msg, str)

    @patch('subprocess.run')
    def test_is_available_with_ffmpeg(self, mock_run):
        """Test is_available when ffmpeg and ffprobe are installed"""
        mock_run.return_value = MagicMock(returncode=0)
        module = VideoEditorModule()
        available, msg = module.is_available()
        assert available is True
        assert "available" in msg.lower()

    @patch('subprocess.run')
    def test_is_available_missing_ffmpeg(self, mock_run):
        """Test is_available when ffmpeg is missing"""
        mock_run.side_effect = FileNotFoundError()
        module = VideoEditorModule()
        available, msg = module.is_available()
        assert available is False
        assert "Missing" in msg

    def test_parse_frame_rate_fraction(self):
        module = VideoEditorModule()
        assert module._parse_frame_rate("30/1") == 30.0
        assert abs(module._parse_frame_rate("30000/1001") - 29.97) < 0.01
        assert module._parse_frame_rate("24/1") == 24.0

    def test_parse_frame_rate_decimal(self):
        module = VideoEditorModule()
        assert module._parse_frame_rate("30.0") == 30.0
        assert module._parse_frame_rate("29.97") == 29.97

    def test_parse_frame_rate_invalid(self):
        module = VideoEditorModule()
        assert module._parse_frame_rate("invalid") == 30.0
        assert module._parse_frame_rate("0/0") == 30.0
        assert module._parse_frame_rate("") == 30.0

    def test_get_words_for_timerange(self):
        module = VideoEditorModule()
        segments = [
            Segment(
                text="Hello world",
                start=0.0,
                end=2.0,
                words=[
                    Word(text="Hello", start=0.0, end=0.5),
                    Word(text="world", start=0.5, end=1.0)
                ]
            ),
            Segment(
                text="How are you",
                start=2.0,
                end=4.0,
                words=[
                    Word(text="How", start=2.0, end=2.3),
                    Word(text="are", start=2.3, end=2.6),
                    Word(text="you", start=2.6, end=3.0)
                ]
            )
        ]

        # Get words from first segment
        words = module._get_words_for_timerange(segments, 0.0, 1.5)
        assert len(words) == 2
        assert words[0].text == "Hello"

        # Get words from second segment
        words = module._get_words_for_timerange(segments, 2.0, 3.5)
        assert len(words) == 3

        # Get no words outside range
        words = module._get_words_for_timerange(segments, 10.0, 15.0)
        assert len(words) == 0

    def test_fallback_moment_detection(self):
        module = VideoEditorModule()
        segments = [
            Segment(text="First segment", start=0.0, end=20.0, words=[]),
            Segment(text="Second segment", start=21.0, end=45.0, words=[]),
            Segment(text="Third segment", start=46.0, end=70.0, words=[]),
        ]

        moments = module._fallback_moment_detection(segments, num_moments=2)
        assert len(moments) <= 2
        for moment in moments:
            assert isinstance(moment, ViralMoment)
            assert moment.end - moment.start >= 15.0  # min_reel_duration

    def test_fallback_moment_detection_empty(self):
        module = VideoEditorModule()
        moments = module._fallback_moment_detection([], num_moments=5)
        assert moments == []

    def test_create_subtitle_filter_empty(self):
        module = VideoEditorModule()
        result = module._create_subtitle_filter([], offset=0.0)
        assert result == ""

    def test_create_subtitle_filter_with_words(self):
        module = VideoEditorModule()
        words = [
            Word(text="Hello", start=1.0, end=1.5),
            Word(text="world", start=1.5, end=2.0)
        ]
        result = module._create_subtitle_filter(words, offset=0.0)
        assert "drawtext" in result
        assert "Hello" in result or "world" in result

    @patch('modules.video_editor.subprocess.run')
    def test_get_video_info_success(self, mock_run):
        """Test _get_video_info with mocked ffprobe output"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format": {"duration": "120.5"}, "streams": [{"codec_type": "video", "width": 1920, "height": 1080, "r_frame_rate": "30/1"}]}'
        )
        module = VideoEditorModule()
        info = module._get_video_info(Path("/fake/video.mp4"))

        assert info["duration"] == 120.5
        assert info["width"] == 1920
        assert info["height"] == 1080
        assert info["fps"] == 30.0

    @patch('modules.video_editor.subprocess.run')
    def test_get_video_info_failure(self, mock_run):
        """Test _get_video_info with ffprobe failure"""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="ffprobe error"
        )
        module = VideoEditorModule()

        with pytest.raises(RuntimeError, match="ffprobe failed"):
            module._get_video_info(Path("/fake/video.mp4"))

    @patch('modules.video_editor.subprocess.run')
    def test_get_video_info_no_video_stream(self, mock_run):
        """Test _get_video_info with no video stream"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format": {"duration": "120.5"}, "streams": [{"codec_type": "audio"}]}'
        )
        module = VideoEditorModule()

        with pytest.raises(ValueError, match="No video stream"):
            module._get_video_info(Path("/fake/video.mp4"))
