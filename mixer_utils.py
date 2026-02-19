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
import xml.etree.ElementTree as ET
from typing import Any

import librosa
import numpy as np
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
