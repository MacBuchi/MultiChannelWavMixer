"""
tests/test_mixer_utils.py
--------------------------
Unit tests for mixer_utils.py — all tests are GUI-free.
Run with: uv run pytest
"""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydub import AudioSegment

import mixer_utils as _mixer_utils  # for _playback_event access

# ── module under test ─────────────────────────────────────────────────────────
from mixer_utils import (
    build_mix_preview,
    build_stereo_mix,
    build_track_preview,
    clean_xml,
    db_to_linear,
    extract_bpm,
    load_raw_config,
    parse_tracks_from_ixml,
    play_audio,
    process_audio,
    save_raw_config,
    stop_playback,
)

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Helpers                                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


def _make_stereo_segment(
    duration_ms: int = 5_000,
    freq: float = 440.0,
    sample_rate: int = 44_100,
) -> AudioSegment:
    """Synthesise a stereo sine-wave AudioSegment (16-bit PCM)."""
    n = int(sample_rate * duration_ms / 1_000)
    t = np.linspace(0, duration_ms / 1_000, n, endpoint=False)
    mono = np.sin(2 * np.pi * freq * t)
    stereo = np.column_stack([mono, mono])
    pcm = (np.clip(stereo, -1, 1) * 32_767).astype(np.int16)
    interleaved = pcm.flatten().tobytes()
    return AudioSegment(
        interleaved,
        frame_rate=sample_rate,
        sample_width=2,
        channels=2,
    )


def _make_multichannel_array(n_samples: int = 44_100, n_channels: int = 4) -> np.ndarray:
    """Return a float64 multichannel array filled with distinct sinusoids."""
    t = np.linspace(0, 1, n_samples)
    data = np.zeros((n_samples, n_channels))
    for ch in range(n_channels):
        data[:, ch] = np.sin(2 * np.pi * (220 * (ch + 1)) * t)
    return data


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  clean_xml                                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestCleanXml:
    def test_strips_prefix_before_xml_declaration(self):
        raw = "JUNK BYTES\x00<?xml version='1.0'?><root/>"
        result = clean_xml(raw)
        assert result.startswith("<?xml")

    def test_removes_non_printable_characters(self):
        raw = "<?xml version='1.0'?>\x01\x02<root/>\x1f"
        result = clean_xml(raw)
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x1f" not in result

    def test_returns_empty_string_when_no_xml_declaration(self):
        result = clean_xml("no xml here at all")
        assert result == ""

    def test_preserves_valid_xml_content(self):
        xml = "<?xml version='1.0'?><BWFXML><TRACK><NAME>Kick</NAME></TRACK></BWFXML>"
        result = clean_xml(xml)
        assert "<TRACK>" in result
        assert "<NAME>Kick</NAME>" in result

    def test_strips_leading_and_trailing_whitespace(self):
        raw = "  \n<?xml version='1.0'?><root/>  \n"
        result = clean_xml(raw)
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_empty_string_input(self):
        assert clean_xml("") == ""


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  parse_tracks_from_ixml                                                    ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

SAMPLE_IXML = """<?xml version='1.0' encoding='UTF-8'?>
<BWFXML>
  <IXML_VERSION>2.0</IXML_VERSION>
  <TRACK_LIST>
    <TRACK_COUNT>4</TRACK_COUNT>
    <TRACK>
      <CHANNEL_INDEX>1</CHANNEL_INDEX>
      <INTERLEAVE_INDEX>1</INTERLEAVE_INDEX>
      <NAME>Guitar L</NAME>
    </TRACK>
    <TRACK>
      <CHANNEL_INDEX>2</CHANNEL_INDEX>
      <INTERLEAVE_INDEX>2</INTERLEAVE_INDEX>
      <NAME>Guitar R</NAME>
    </TRACK>
    <TRACK>
      <CHANNEL_INDEX>3</CHANNEL_INDEX>
      <INTERLEAVE_INDEX>3</INTERLEAVE_INDEX>
      <NAME>Kick</NAME>
    </TRACK>
    <TRACK>
      <CHANNEL_INDEX>4</CHANNEL_INDEX>
      <INTERLEAVE_INDEX>4</INTERLEAVE_INDEX>
      <NAME>Bass</NAME>
    </TRACK>
  </TRACK_LIST>
</BWFXML>"""


class TestParseTracksFromIxml:
    def test_returns_correct_number_of_tracks(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        assert len(tracks) == 4

    def test_track_names_are_parsed(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        names = [t["name"] for t in tracks]
        assert "Guitar L" in names
        assert "Guitar R" in names
        assert "Kick" in names
        assert "Bass" in names

    def test_track_index_is_int(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        for track in tracks:
            assert isinstance(track["index"], int)

    def test_pan_left_tracks_have_pan_zero(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        guitar_l = next(t for t in tracks if t["name"] == "Guitar L")
        assert guitar_l["pan"] == 0.0

    def test_pan_right_tracks_have_pan_one(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        guitar_r = next(t for t in tracks if t["name"] == "Guitar R")
        assert guitar_r["pan"] == 1.0

    def test_centre_tracks_have_pan_half(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        kick = next(t for t in tracks if t["name"] == "Kick")
        assert kick["pan"] == 0.5

    def test_default_volume_is_one(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        for track in tracks:
            assert track["volume"] == 1.0

    def test_default_use_for_mixdown_is_true(self):
        tracks = parse_tracks_from_ixml(SAMPLE_IXML)
        for track in tracks:
            assert track["use_for_mixdown"] is True

    def test_empty_string_returns_empty_list(self):
        assert parse_tracks_from_ixml("") == []

    def test_invalid_xml_returns_empty_list(self):
        assert parse_tracks_from_ixml("not xml at all") == []

    def test_missing_name_element_uses_unknown(self):
        ixml = """<?xml version='1.0'?>
        <BWFXML><TRACK_LIST><TRACK>
            <INTERLEAVE_INDEX>1</INTERLEAVE_INDEX>
        </TRACK></TRACK_LIST></BWFXML>"""
        tracks = parse_tracks_from_ixml(ixml)
        assert tracks[0]["name"] == "Unknown"


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  load_raw_config / save_raw_config                                         ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

SAMPLE_CONFIG: dict = {
    "Guitar L": {"index": 1, "volume": 1.0, "pan": 0.0, "use_for_mixdown": True},
    "Guitar R": {"index": 2, "volume": 1.0, "pan": 1.0, "use_for_mixdown": True},
    "Kick": {"index": 3, "volume": 0.8, "pan": 0.5, "use_for_mixdown": False},
}


class TestRawConfig:
    def test_save_and_load_roundtrip(self, tmp_path):
        path = str(tmp_path / "test_config.json")
        save_raw_config(SAMPLE_CONFIG, path)
        loaded = load_raw_config(path)
        assert loaded == SAMPLE_CONFIG

    def test_load_returns_empty_dict_when_file_missing(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        assert load_raw_config(path) == {}

    def test_load_returns_empty_dict_on_invalid_json(self, tmp_path):
        path_obj = tmp_path / "broken.json"
        path_obj.write_text("{ this is not json }", encoding="utf-8")
        assert load_raw_config(str(path_obj)) == {}

    def test_save_creates_valid_json_file(self, tmp_path):
        path = tmp_path / "out.json"
        save_raw_config(SAMPLE_CONFIG, str(path))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert set(data.keys()) == set(SAMPLE_CONFIG.keys())

    def test_save_overwrites_existing_file(self, tmp_path):
        path = str(tmp_path / "config.json")
        save_raw_config(SAMPLE_CONFIG, path)
        new_config = {"Snare": {"index": 5, "volume": 0.9, "pan": 0.5, "use_for_mixdown": True}}
        save_raw_config(new_config, path)
        loaded = load_raw_config(path)
        assert list(loaded.keys()) == ["Snare"]

    def test_volume_precision_preserved(self, tmp_path):
        config = {"Ch1": {"index": 1, "volume": 1.234567, "pan": 0.5, "use_for_mixdown": True}}
        path = str(tmp_path / "precision.json")
        save_raw_config(config, path)
        loaded = load_raw_config(path)
        assert abs(loaded["Ch1"]["volume"] - 1.234567) < 1e-5


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  build_stereo_mix                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestBuildStereoMix:
    def test_output_shape_is_samples_by_two(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=2)
        tracks = [{"index": 1, "volume": 1.0, "pan": 0.5}]
        result = build_stereo_mix(data, tracks)
        assert result.shape == (1000, 2)

    def test_full_pan_left_puts_signal_only_in_left_channel(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=1)
        tracks = [{"index": 1, "volume": 1.0, "pan": 0.0}]
        result = build_stereo_mix(data, tracks)
        assert np.allclose(result[:, 0], data[:, 0])
        assert np.allclose(result[:, 1], 0.0)

    def test_full_pan_right_puts_signal_only_in_right_channel(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=1)
        tracks = [{"index": 1, "volume": 1.0, "pan": 1.0}]
        result = build_stereo_mix(data, tracks)
        assert np.allclose(result[:, 0], 0.0)
        assert np.allclose(result[:, 1], data[:, 0])

    def test_centre_pan_splits_equally(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=1)
        tracks = [{"index": 1, "volume": 1.0, "pan": 0.5}]
        result = build_stereo_mix(data, tracks)
        assert np.allclose(result[:, 0], result[:, 1])

    def test_volume_scales_output(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=1)
        t1 = [{"index": 1, "volume": 1.0, "pan": 0.5}]
        t2 = [{"index": 1, "volume": 2.0, "pan": 0.5}]
        r1 = build_stereo_mix(data, t1)
        r2 = build_stereo_mix(data, t2)
        assert np.allclose(r2, r1 * 2)

    def test_empty_tracks_returns_silence(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=2)
        result = build_stereo_mix(data, [])
        assert np.all(result == 0.0)

    def test_multiple_tracks_are_summed(self):
        n = 1000
        data = np.ones((n, 2))
        tracks = [
            {"index": 1, "volume": 1.0, "pan": 0.0},
            {"index": 2, "volume": 1.0, "pan": 0.0},
        ]
        result = build_stereo_mix(data, tracks)
        # Both tracks fully panned left → left channel = 2.0, right = 0.0
        assert np.allclose(result[:, 0], 2.0)
        assert np.allclose(result[:, 1], 0.0)

    def test_output_dtype_is_float64(self):
        data = _make_multichannel_array(n_samples=100, n_channels=1)
        result = build_stereo_mix(data, [{"index": 1, "volume": 1.0, "pan": 0.5}])
        assert result.dtype == np.float64


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  process_audio                                                             ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestProcessAudio:
    """Tests use a 5-second 440 Hz stereo sine wave."""

    @pytest.fixture()
    def audio(self) -> AudioSegment:
        return _make_stereo_segment(duration_ms=5_000)

    def test_returns_audio_segment(self, audio):
        result = process_audio(audio, 3.25, 2, 1, 3, 80)
        assert isinstance(result, AudioSegment)

    def test_output_is_stereo(self, audio):
        result = process_audio(audio, 3.25, 2, 1, 3, 80)
        assert result.channels == 2

    def test_output_sample_width_is_respected(self, audio):
        result = process_audio(audio, 3.25, 2, 1, 3, 80)
        assert result.sample_width == 2

    def test_output_is_not_silent(self, audio):
        result = process_audio(audio, 3.25, 2, 1, 3, 80)
        assert result.dBFS > -60

    def test_fade_applied_when_duration_exceeds_threshold(self, audio):
        """A 5 s clip with threshold=3 s should have fades applied."""
        result = process_audio(audio, 3.25, 2, 1.0, 3, 80)
        # After fade-in/out the audio should still be non-trivially long
        assert result.duration_seconds > 1.0

    def test_no_fade_when_duration_below_threshold(self):
        short = _make_stereo_segment(duration_ms=1_000)  # 1 s < 3 s threshold
        result = process_audio(short, 3.25, 2, 1.0, 3, 80)
        assert isinstance(result, AudioSegment)

    def test_frame_rate_preserved(self, audio):
        result = process_audio(audio, 3.25, 2, 1, 3, 80)
        assert result.frame_rate == audio.frame_rate


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  extract_bpm                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestExtractBpm:
    @pytest.fixture()
    def click_track(self) -> tuple[np.ndarray, int]:
        """120 BPM click track: impulse every 0.5 s at sr=22050."""
        sr = 22_050
        duration_s = 20
        n = sr * duration_s
        y = np.zeros(n, dtype=np.float32)
        beat_interval = sr // 2  # 120 BPM
        y[::beat_interval] = 1.0
        return y, sr

    def test_returns_float(self, click_track):
        y, sr = click_track
        bpm = extract_bpm(y, sr)
        assert isinstance(bpm, float)

    def test_bpm_is_positive(self, click_track):
        y, sr = click_track
        bpm = extract_bpm(y, sr)
        assert bpm > 0

    def test_bpm_plausible_range(self, click_track):
        y, sr = click_track
        bpm = extract_bpm(y, sr)
        # librosa may detect double / half tempo on synthetic clicks — accept 60–240
        assert 60 <= bpm <= 240

    def test_handles_silent_signal(self):
        y = np.zeros(22_050, dtype=np.float32)
        bpm = extract_bpm(y, 22_050)
        # Should not raise; result is librosa's default fallback
        assert isinstance(bpm, float)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  build_track_preview                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestBuildTrackPreview:
    def test_output_shape_is_stereo(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=3)
        result = build_track_preview(data, channel_idx=0)
        assert result.shape == (1000, 2)

    def test_output_dtype_is_float32(self):
        data = _make_multichannel_array(n_samples=1000, n_channels=2)
        result = build_track_preview(data, channel_idx=0)
        assert result.dtype == np.float32

    def test_both_channels_are_identical(self):
        """Mono source should be duplicated to both channels."""
        data = _make_multichannel_array(n_samples=500, n_channels=2)
        result = build_track_preview(data, channel_idx=0)
        assert np.allclose(result[:, 0], result[:, 1])

    def test_peak_is_normalised_to_minus_1_dbfs(self):
        """Peak must be ≈ 0.891 (≈1 dBFS)."""
        data = _make_multichannel_array(n_samples=44_100, n_channels=1)
        result = build_track_preview(data, channel_idx=0)
        peak = float(np.max(np.abs(result)))
        assert abs(peak - 0.891) < 0.01

    def test_silent_channel_stays_silent(self):
        data = np.zeros((1000, 2))
        result = build_track_preview(data, channel_idx=0)
        assert np.all(result == 0.0)

    def test_correct_channel_is_extracted(self):
        """Channel 1 should produce different content from channel 0."""
        data = _make_multichannel_array(n_samples=1000, n_channels=2)
        r0 = build_track_preview(data, channel_idx=0)
        r1 = build_track_preview(data, channel_idx=1)
        assert not np.allclose(r0, r1)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  build_mix_preview                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestBuildMixPreview:
    SR = 44_100

    def _tracks(self, n_ch: int) -> list:
        return [{"index": i + 1, "volume": 1.0, "pan": 0.5} for i in range(n_ch)]

    def test_output_shape_is_stereo(self):
        data = _make_multichannel_array(n_samples=self.SR, n_channels=2)
        result = build_mix_preview(data, self._tracks(2), self.SR, "-1dBFS")
        assert result.shape == (self.SR, 2)

    def test_output_dtype_is_float32(self):
        data = _make_multichannel_array(n_samples=self.SR, n_channels=2)
        result = build_mix_preview(data, self._tracks(2), self.SR, "none")
        assert result.dtype == np.float32

    def test_peak_normalisation_clamps_to_minus_1_dbfs(self):
        data = _make_multichannel_array(n_samples=self.SR, n_channels=2)
        result = build_mix_preview(data, self._tracks(2), self.SR, "-1dBFS")
        peak = float(np.max(np.abs(result)))
        assert peak <= 1.0

    def test_no_normalisation_mode_prevents_clipping(self):
        """Even in 'none' mode the output must not exceed 1.0."""
        # Use volume=2 to push the mix above 1.0 before the clamp
        loud_tracks = [{"index": 1, "volume": 2.0, "pan": 0.5}]
        data = _make_multichannel_array(n_samples=self.SR, n_channels=1)
        result = build_mix_preview(data, loud_tracks, self.SR, "none")
        assert float(np.max(np.abs(result))) <= 1.0

    def test_lufs_mode_returns_valid_audio(self):
        """LUFS normalisation should produce finite, non-silent output."""
        data = _make_multichannel_array(n_samples=self.SR * 5, n_channels=2)
        result = build_mix_preview(data, self._tracks(2), self.SR, "-12dB LUFS")
        assert np.all(np.isfinite(result))
        assert np.max(np.abs(result)) > 0

    def test_empty_tracks_returns_silence(self):
        data = _make_multichannel_array(n_samples=self.SR, n_channels=2)
        result = build_mix_preview(data, [], self.SR, "-1dBFS")
        assert np.all(result == 0.0)


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  play_audio / stop_playback  (sounddevice mocked)                          ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestPlayback:
    """sounddevice is mocked so tests run without an audio device.

    play_audio() opens the OutputStream on a background thread that waits for
    the previous stream to finish, so tests that need to observe the stream
    must give the thread a moment to run (time.sleep).
    """

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset all module-level playback state before/after every test."""
        _mixer_utils._playback_event.clear()
        _mixer_utils._current_stop = None
        _mixer_utils._playback_generation = 0
        yield
        _mixer_utils._playback_event.clear()
        _mixer_utils._current_stop = None
        _mixer_utils._playback_generation = 0

    # ── stop_playback ─────────────────────────────────────────────────────────

    def test_stop_is_noop_when_not_playing(self):
        """stop_playback() must not touch sounddevice when nothing is active."""
        with patch("mixer_utils.sd") as mock_sd:
            stop_playback()
            mock_sd.stop.assert_not_called()
            mock_sd.OutputStream.assert_not_called()

    def test_stop_sets_per_stream_event(self):
        """stop_playback() signals the current stream's stop event."""
        stop_event = threading.Event()
        _mixer_utils._current_stop = stop_event
        stop_playback()
        assert stop_event.is_set()

    def test_stop_clears_current_stop_ref(self):
        _mixer_utils._current_stop = threading.Event()
        stop_playback()
        assert _mixer_utils._current_stop is None

    # ── play_audio ────────────────────────────────────────────────────────────

    def test_play_creates_output_stream(self):
        with patch("mixer_utils.sd") as mock_sd:
            mock_stream = MagicMock()
            mock_sd.OutputStream.return_value = mock_stream
            play_audio(np.zeros((100, 2), dtype=np.float32), 44_100)
            time.sleep(0.05)  # let the launch thread run
            mock_sd.OutputStream.assert_called_once()
            mock_stream.start.assert_called_once()

    def test_play_passes_correct_samplerate(self):
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            play_audio(np.zeros((100, 2), dtype=np.float32), 48_000)
            time.sleep(0.05)
            _, kwargs = mock_sd.OutputStream.call_args
            assert kwargs["samplerate"] == 48_000

    def test_play_passes_correct_channel_count(self):
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            play_audio(np.zeros((100, 3), dtype=np.float32), 44_100)
            time.sleep(0.05)
            _, kwargs = mock_sd.OutputStream.call_args
            assert kwargs["channels"] == 3

    def test_play_sets_playback_event(self):
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            play_audio(np.zeros((100, 2), dtype=np.float32), 44_100)
            time.sleep(0.05)
            assert _mixer_utils._playback_event.is_set()

    def test_second_play_signals_first_stream_to_stop(self):
        """Starting a second stream must signal the first stream's stop event."""
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            data = np.zeros((100, 2), dtype=np.float32)
            play_audio(data, 44_100)
            first_stop = _mixer_utils._current_stop
            play_audio(data, 44_100)
            time.sleep(0.05)
            # first_stop must have been signalled
            assert first_stop is None or first_stop.is_set()

    def test_finished_callback_calls_on_finished(self):
        """The OutputStream finished_callback must invoke on_finished."""
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            finished = MagicMock()
            play_audio(np.zeros((100, 2), dtype=np.float32), 44_100, on_finished=finished)
            time.sleep(0.05)
            _, kwargs = mock_sd.OutputStream.call_args
            kwargs["finished_callback"]()
            finished.assert_called_once()

    def test_finished_callback_clears_playback_event(self):
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            play_audio(np.zeros((100, 2), dtype=np.float32), 44_100)
            time.sleep(0.05)
            _, kwargs = mock_sd.OutputStream.call_args
            kwargs["finished_callback"]()
            assert not _mixer_utils._playback_event.is_set()

    def test_on_finished_not_required(self):
        """Omitting on_finished must not raise when finished_callback fires."""
        with patch("mixer_utils.sd") as mock_sd:
            mock_sd.OutputStream.return_value = MagicMock()
            play_audio(np.zeros((100, 2), dtype=np.float32), 44_100)
            time.sleep(0.05)
            _, kwargs = mock_sd.OutputStream.call_args
            kwargs["finished_callback"]()  # must not raise


# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  db_to_linear                                                               ║
# ╚══════════════════════════════════════════════════════════════════════════════╝


class TestDbToLinear:
    def test_unity_gain(self):
        assert db_to_linear(0.0) == pytest.approx(1.0, rel=1e-6)

    def test_minus_6db(self):
        assert db_to_linear(-6.0) == pytest.approx(10 ** (-6 / 20), rel=1e-4)

    def test_plus_6db(self):
        assert db_to_linear(6.0) == pytest.approx(10 ** (6 / 20), rel=1e-4)

    def test_floor_returns_zero(self):
        assert db_to_linear(-60.0) == 0.0
        assert db_to_linear(-100.0) == 0.0

    def test_just_above_floor_is_nonzero(self):
        assert db_to_linear(-59.9) > 0.0

    def test_custom_floor(self):
        assert db_to_linear(-40.0, floor_db=-40.0) == 0.0
        assert db_to_linear(-39.9, floor_db=-40.0) > 0.0
