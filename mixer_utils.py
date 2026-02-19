"""
mixer_utils.py
--------------
Pure utility functions for MultiChannelWavMixer.
No GUI / tkinter dependency — safe to import in tests.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable

import librosa
import numpy as np
import sounddevice as sd
from pydub import AudioSegment, effects, silence

# ── XML / iXML helpers ──────────────────────────────────────────────────────────

def clean_xml(data: str) -> str:
    """Strip everything before ``<?xml`` and remove non-printable characters."""
    start = data.find("<?xml")
    if start == -1:
        return ""
    data = data[start:]
    data = re.sub(r"[^\x20-\x7E]+", "", data)
    return data.strip()


def parse_tracks_from_ixml(ixml_str: str) -> list[dict[str, Any]]:
    """
    Parse a cleaned iXML string and return a list of plain-dict track descriptors.

    Each dict contains:
        index (int), name (str), volume (float), pan (float), use_for_mixdown (bool)

    Pan heuristic: names ending in \" L\" → 0.0, \" R\" → 1.0, otherwise 0.5.
    """
    if not ixml_str:
        return []

    try:
        root = ET.fromstring(ixml_str)
    except ET.ParseError:
        return []

    raw: list[tuple[str, str]] = []
    for track in root.findall(".//TRACK"):
        name_el = track.find("NAME")
        idx_el = track.find("INTERLEAVE_INDEX")
        name = name_el.text if name_el is not None else "Unknown"
        index = idx_el.text if idx_el is not None else "0"
        raw.append((index, name))

    result: list[dict[str, Any]] = []
    for index_str, name in raw:
        if name.endswith(" L"):
            pan = 0.0
        elif name.endswith(" R"):
            pan = 1.0
        else:
            pan = 0.5
        result.append({
            "index": int(index_str),
            "name": name,
            "volume": 1.0,
            "pan": pan,
            "use_for_mixdown": True,
        })
    return result


# ── Config I/O (plain dicts – no tkinter) ───────────────────────────────────────

def load_raw_config(path: str = "MixConf.json") -> dict[str, dict[str, Any]]:
    """Load *path* and return the channel config as plain Python dicts."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_raw_config(config: dict[str, dict[str, Any]], path: str = "MixConf.json") -> None:
    """Write channel config (plain Python dicts) to *path*."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


# ── Stereo mixing ────────────────────────────────────────────────────────────────

def build_stereo_mix(
    data: np.ndarray,
    active_tracks: list[dict[str, Any]],
) -> np.ndarray:
    """
    Downmix multichannel PCM *data* (shape ``[samples, channels]``) to stereo.

    *active_tracks* is a list of plain dicts:
        ``{"index": int (1-based), "volume": float, "pan": float}``

    Returns a ``float64`` array of shape ``[samples, 2]``.
    """
    stereo = np.zeros((data.shape[0], 2), dtype=np.float64)
    for track in active_tracks:
        idx = int(track["index"]) - 1
        volume = float(track["volume"])
        pan = float(track["pan"])
        stereo[:, 0] += data[:, idx] * volume * (1.0 - pan)
        stereo[:, 1] += data[:, idx] * volume * pan
    return stereo


# ── Audio post-processing ────────────────────────────────────────────────────────

def process_audio(
    wav_in: AudioSegment,
    PHASE_DBFS_THRESH: float,
    SAMPLE_WIDTH: int,
    NORMALIZATION_HEADROOM: float,
    APPLY_FADE_LEN_THRESH_S: float,
    FADE_DURATION: int,
) -> AudioSegment:
    """
    Post-process a stereo ``AudioSegment``:

    1. Detect and fix phase inversion (mono-sum dBFS check).
    2. Normalise with *NORMALIZATION_HEADROOM* dB of headroom.
    3. Strip leading silence.
    4. Apply fade-in / fade-out if duration > *APPLY_FADE_LEN_THRESH_S*.
    """
    stereo_sound_mono = wav_in.split_to_mono()[0]
    phase_diff = wav_in.dBFS - stereo_sound_mono.dBFS
    has_phase_issues = abs(phase_diff) > PHASE_DBFS_THRESH

    if has_phase_issues:
        split = wav_in.split_to_mono()
        stereo_sound = AudioSegment.from_mono_audiosegments(
            split[0], split[1].invert_phase()
        )
    else:
        stereo_sound = wav_in.set_channels(2)

    stereo_sound = stereo_sound.set_sample_width(SAMPLE_WIDTH)
    stereo_sound = effects.normalize(stereo_sound, headroom=NORMALIZATION_HEADROOM)

    leading_silence_end = silence.detect_leading_silence(stereo_sound)
    stereo_sound = stereo_sound[leading_silence_end:]

    if round(stereo_sound.duration_seconds, 2) > APPLY_FADE_LEN_THRESH_S:
        stereo_sound = stereo_sound.fade_in(FADE_DURATION).fade_out(FADE_DURATION)

    return stereo_sound


# ── BPM detection ────────────────────────────────────────────────────────────────

def extract_bpm(y: np.ndarray, sr: int) -> float:
    """Return the estimated tempo in BPM using librosa's beat tracker."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    return float(np.atleast_1d(tempo)[0])


# ── Playback ─────────────────────────────────────────────────────────────────
#
# Design goals:
#  1. Only one stream is ever open at a time.
#  2. Stop is signalled via a per-stream Event checked inside the *audio
#     callback*, so Pa_StopStream is never called externally (avoids AUHAL -50).
#  3. Starting a new stream while one is running is deadlock-free: the launch
#     thread waits (polling, ≤200 ms) for the old stream's finished_callback to
#     confirm teardown before opening a new OutputStream.
#  4. A generation counter ensures only the *latest* click's background thread
#     opens a stream; superseded threads exit silently.

_playback_event: threading.Event = threading.Event()   # set ↔ stream is alive
_current_stop: threading.Event | None = None            # signal current stream
_playback_generation: int = 0                           # incremented on each launch
_playback_lock: threading.Lock = threading.Lock()       # guards above globals
_active_stream: object | None = None                    # keeps OutputStream alive


def db_to_linear(db: float, floor_db: float = -60.0) -> float:
    """Convert a dB value to a linear amplitude multiplier.

    Values at or below *floor_db* return 0.0 (treated as silence).
    """
    if db <= floor_db:
        return 0.0
    return float(10.0 ** (db / 20.0))


def play_audio(
    data: np.ndarray,
    samplerate: int,
    on_finished: Callable | None = None,
) -> None:
    """
    Play *data* (float32/64, mono or stereo) non-blocking.

    * Only one stream is open at a time — calling this while something is
      already playing stops the previous stream first.
    * Stopping uses a per-stream ``threading.Event`` checked by the audio
      callback, so ``Pa_StopStream`` is never called (no AUHAL -50 on macOS).
    * The actual ``sd.OutputStream`` is opened on a background thread that
      waits for the previous stream to fully teardown before proceeding.
    """
    global _current_stop, _playback_generation

    with _playback_lock:
        # Signal the running stream (if any) to stop gracefully.
        if _current_stop is not None:
            _current_stop.set()
        # Bump the generation so any previous pending launch thread exits.
        _playback_generation += 1
        my_generation = _playback_generation
        my_stop = threading.Event()
        _current_stop = my_stop

    buf = data.astype(np.float32)
    channels = buf.shape[1] if buf.ndim > 1 else 1
    n_frames = len(buf)

    def _launch() -> None:
        # Wait for the previous stream's finished_callback to fire (≤200 ms).
        deadline = time.monotonic() + 0.2
        while _playback_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)

        # If a newer click arrived while we were waiting, bail out.
        with _playback_lock:
            if _playback_generation != my_generation:
                return

        pos = [0]
        _playback_event.set()

        def _callback(outdata: np.ndarray, frames: int, time_info, status) -> None:  # noqa: ARG001
            if my_stop.is_set():
                outdata[:] = 0
                raise sd.CallbackStop()
            remaining = n_frames - pos[0]
            if remaining <= 0:
                outdata[:] = 0
                raise sd.CallbackStop()
            take = min(frames, remaining)
            outdata[:take] = buf[pos[0] : pos[0] + take]
            if take < frames:
                outdata[take:] = 0
            pos[0] += take

        def _finished() -> None:
            global _active_stream
            _active_stream = None          # release the stream ref *after* PA is done
            _playback_event.clear()
            if on_finished:
                on_finished()

        global _active_stream
        stream = sd.OutputStream(
            samplerate=samplerate,
            channels=channels,
            callback=_callback,
            finished_callback=_finished,
            dtype="float32",
        )
        _active_stream = stream            # prevent GC while callback is alive
        stream.start()

    threading.Thread(target=_launch, daemon=True).start()


def stop_playback() -> None:
    """Signal the active stream's callback to stop on its next buffer.

    Thread-safe and always a no-op when nothing is playing.  Never calls
    ``Pa_StopStream``, so the AUHAL error -50 on macOS does not occur.
    """
    global _current_stop
    with _playback_lock:
        if _current_stop is not None:
            _current_stop.set()
            _current_stop = None


def build_track_preview(data: np.ndarray, channel_idx: int) -> np.ndarray:
    """
    Extract *channel_idx* (0-based) from multichannel *data* and return a
    stereo float32 array normalised to -1 dBFS peak for comfortable listening.
    Note: normalisation here is only for audition comfort; it does NOT reflect
    the channel's fader level — that is applied only in the mix pipeline.
    """
    mono = data[:, channel_idx].astype(np.float64)
    peak = np.max(np.abs(mono))
    if peak > 0:
        mono = mono / peak * 0.891  # -1 dBFS
    return np.column_stack([mono, mono]).astype(np.float32)


def build_mix_preview(
    data: np.ndarray,
    active_tracks: list[dict[str, Any]],
    samplerate: int,
    loudness_mode: str,
) -> np.ndarray:
    """
    Build a normalised stereo float32 preview mix ready for sounddevice playback.
    Falls back to peak normalisation when LUFS measurement is unreliable.
    """
    import pyloudnorm as pyln

    stereo = build_stereo_mix(data, active_tracks)  # float64

    # Guard: silent mix — skip normalisation to avoid divide-by-zero
    if np.max(np.abs(stereo)) == 0.0:
        return stereo.astype(np.float32)

    if loudness_mode == "-1dBFS":
        stereo = pyln.normalize.peak(stereo, -1.0)
    elif loudness_mode == "-12dB LUFS":
        meter = pyln.Meter(samplerate)
        try:
            loudness = meter.integrated_loudness(stereo)
            if np.isfinite(loudness):
                stereo = pyln.normalize.loudness(stereo, loudness, -12.0)
            else:
                stereo = pyln.normalize.peak(stereo, -1.0)
        except Exception:
            stereo = pyln.normalize.peak(stereo, -1.0)
    else:
        # no normalisation — still protect against clipping
        peak = np.max(np.abs(stereo))
        if peak > 1.0:
            stereo = stereo / peak

    return stereo.astype(np.float32)
