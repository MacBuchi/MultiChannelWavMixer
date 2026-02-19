import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import soundfile as sf
import numpy as np
import os
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pyloudnorm as pyln
import librosa

from mixer_utils import (
    clean_xml,
    parse_tracks_from_ixml,
    load_raw_config,
    save_raw_config,
    build_stereo_mix,
    process_audio,
    extract_bpm,
    play_audio,
    stop_playback,
    build_track_preview,
    build_mix_preview,
)

# ─── Appearance ────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─── Constants ─────────────────────────────────────────────────────────────────
CONFIG_FILE = "MixConf.json"

def load_mix_config():
    """Load MixConf.json and return a dict of channel data wrapped in tkinter variables."""
    raw = load_raw_config(CONFIG_FILE)
    mix_config = {}
    for name, values in raw.items():
        mix_config[name] = {
            "index": tk.IntVar(value=values.get("index", 0)),
            "volume": tk.DoubleVar(value=values.get("volume", 1.0)),
            "pan": tk.DoubleVar(value=values.get("pan", 0.5)),
            "use_for_mixdown": tk.BooleanVar(value=values.get("use_for_mixdown", True)),
        }
    return mix_config

def save_mix_config(mix_config):
    """Unwrap tkinter variables and persist channel config to MixConf.json."""
    raw_config = {
        name: {
            "index": values["index"].get() if isinstance(values["index"], tk.IntVar) else values["index"],
            "volume": values["volume"].get() if isinstance(values["volume"], tk.DoubleVar) else values["volume"],
            "pan": values["pan"].get() if isinstance(values["pan"], tk.DoubleVar) else values["pan"],
            "use_for_mixdown": values["use_for_mixdown"].get() if isinstance(values["use_for_mixdown"], tk.BooleanVar) else values["use_for_mixdown"],
        }
        for name, values in mix_config.items()
    }
    save_raw_config(raw_config, CONFIG_FILE)

def parse_ixml(file_path: str) -> list:
    """Read iXML metadata from *file_path* and return tracks wrapped in tkinter variables."""
    with open(file_path, "rb") as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b"\n":
            f.seek(-2, os.SEEK_CUR)
        ixml_data = f.readline().decode("utf-8", errors="ignore").strip()

    ixml_data = clean_xml(ixml_data)
    plain_tracks = parse_tracks_from_ixml(ixml_data)

    return [
        {
            "index": tk.IntVar(value=t["index"]),
            "name": t["name"],
            "volume": tk.DoubleVar(value=t["volume"]),
            "pan": tk.DoubleVar(value=t["pan"]),
            "use_for_mixdown": tk.BooleanVar(value=t["use_for_mixdown"]),
        }
        for t in plain_tracks
    ]

# ─── UI callback functions ─────────────────────────────────────────────────────

def load_wav():
    """Open one or more WAV files, parse iXML metadata and populate the track list."""
    global file_paths
    file_paths = filedialog.askopenfilenames(filetypes=[("WAV files", "*.wav")])
    if not file_paths:
        return

    global tracks
    file_path = file_paths[0]
    tracks = parse_ixml(file_path)
    mix_config = load_mix_config()

    for track in tracks:
        name = track["name"]
        if name in mix_config:
            track.update(mix_config[name])

    global _wav_data, _wav_samplerate
    _wav_data, _wav_samplerate = sf.read(file_path, dtype="float64")

    _rebuild_track_rows()

    path = os.path.dirname(file_path)
    set_output_folder(path)
    btn_preview.configure(state="normal")
    btn_listen_mix.configure(state="normal")


def _rebuild_track_rows():
    """Clear the scrollable frame and redraw all track rows."""
    for widget in frame_controls.winfo_children():
        widget.destroy()

    # ── Header row ──────────────────────────────────────────────────────────
    HEADER_FONT = ctk.CTkFont(size=12, weight="bold")
    headers    = ["#",  "Mix", "Track Name", "Volume", "",   "Pan", "",   "Play"]
    col_widths = [ 40,   40,    185,           120,      38,   120,   38,   42  ]
    for col, (text, w) in enumerate(zip(headers, col_widths)):
        ctk.CTkLabel(
            frame_controls, text=text, width=w,
            font=HEADER_FONT, text_color=("gray60", "gray50")
        ).grid(row=0, column=col, padx=(4, 2), pady=(6, 4), sticky="w")

    # ── Track rows ───────────────────────────────────────────────────────────
    for i, track in enumerate(tracks, start=1):
        row_bg = ("gray90", "gray17") if i % 2 == 0 else ("gray95", "gray20")

        # Index entry
        ctk.CTkEntry(
            frame_controls, width=40, height=28,
            textvariable=track["index"], justify="center"
        ).grid(row=i, column=0, padx=(4, 2), pady=3, sticky="w")

        # Mixdown checkbox
        ctk.CTkCheckBox(
            frame_controls, text="", width=28, height=28,
            variable=track["use_for_mixdown"],
            onvalue=True, offvalue=False
        ).grid(row=i, column=1, padx=(2, 2), pady=3)

        # Track name
        ctk.CTkLabel(
            frame_controls, text=track["name"], width=185,
            anchor="w", font=ctk.CTkFont(size=12)
        ).grid(row=i, column=2, padx=(4, 8), pady=3, sticky="w")

        # Volume slider + live value label
        vol_var = track["volume"]
        vol_str = tk.StringVar(value=f"{vol_var.get():.2f}")
        vol_var.trace_add("write", lambda *_, v=vol_var, s=vol_str: s.set(f"{v.get():.2f}"))

        vol_slider = ctk.CTkSlider(
            frame_controls, from_=0, to=2, width=120,
            variable=vol_var, number_of_steps=200
        )
        vol_slider.grid(row=i, column=3, padx=(2, 2), pady=3)
        vol_slider.bind("<Double-Button-1>",
                        lambda e, v=vol_var: v.set(1.0))

        ctk.CTkLabel(
            frame_controls, textvariable=vol_str, width=38,
            font=ctk.CTkFont(size=11), text_color=("gray40", "gray70"), anchor="w"
        ).grid(row=i, column=4, padx=(0, 6), pady=3, sticky="w")

        # Pan slider + live value label
        pan_var = track["pan"]
        pan_str = tk.StringVar(value=f"{pan_var.get():.2f}")
        pan_var.trace_add("write", lambda *_, v=pan_var, s=pan_str: s.set(f"{v.get():.2f}"))

        pan_slider = ctk.CTkSlider(
            frame_controls, from_=0, to=1, width=120,
            variable=pan_var, number_of_steps=100
        )
        pan_slider.grid(row=i, column=5, padx=(2, 2), pady=3)
        pan_slider.bind("<Double-Button-1>",
                        lambda e, v=pan_var: v.set(0.5))

        ctk.CTkLabel(
            frame_controls, textvariable=pan_str, width=38,
            font=ctk.CTkFont(size=11), text_color=("gray40", "gray70"), anchor="w"
        ).grid(row=i, column=6, padx=(0, 4), pady=3, sticky="w")

        # Per-track play button
        play_btn = ctk.CTkButton(
            frame_controls, text="\u25b6", width=34, height=28,
            font=ctk.CTkFont(size=11),
            fg_color=("gray70", "gray30"),
            hover_color=("gray55", "gray45"),
            text_color=("gray15", "gray90"),
        )
        play_btn.configure(command=lambda t=track, b=play_btn: _toggle_track_play(t, b))
        play_btn.grid(row=i, column=7, padx=(6, 4), pady=3)


def _reset_active_btn() -> None:
    """Reset the currently active play button back to ▶ (safe to call from any thread via root.after)."""
    global _active_play_btn
    if _active_play_btn is not None:
        try:
            _active_play_btn.configure(text="\u25b6")
        except Exception:
            pass
        _active_play_btn = None


def _toggle_track_play(track: dict, btn) -> None:
    """Play / stop a single track channel."""
    global _active_play_btn, _wav_data, _wav_samplerate
    if _active_play_btn is btn:
        # second click on same button → stop
        stop_playback()
        _reset_active_btn()
        return
    # stop whatever was playing before
    stop_playback()
    _reset_active_btn()
    if _wav_data is None:
        return
    idx = track["index"].get() - 1
    preview = build_track_preview(_wav_data, idx)
    _active_play_btn = btn
    btn.configure(text="\u25a0")
    play_audio(preview, _wav_samplerate,
               on_finished=lambda: root.after(0, _reset_active_btn))


def preview_mix() -> None:
    """Build a normalised stereo preview of the current mix and play it."""
    global _active_play_btn, _wav_data, _wav_samplerate
    if _wav_data is None:
        return
    stop_playback()
    _reset_active_btn()
    active_tracks = [
        {"index": t["index"].get(), "volume": t["volume"].get(), "pan": t["pan"].get()}
        for t in tracks if t["use_for_mixdown"].get()
    ]
    if not active_tracks:
        messagebox.showwarning("Preview Mix", "No tracks selected for mixdown.")
        return
    preview = build_mix_preview(_wav_data, active_tracks, _wav_samplerate, loudness_option.get())
    _active_play_btn = btn_listen_mix
    btn_listen_mix.configure(text="\u25a0 Stop")
    play_audio(preview, _wav_samplerate,
               on_finished=lambda: root.after(0, _reset_listen_mix_btn))


def _reset_listen_mix_btn() -> None:
    global _active_play_btn
    try:
        btn_listen_mix.configure(text="Listen Mix \u25b6")
    except Exception:
        pass
    if _active_play_btn is btn_listen_mix:
        _active_play_btn = None


def update_mix_config():
    """Persist current GUI values to MixConf.json."""
    mix_config = load_mix_config()
    for track in tracks:
        mix_config[track["name"]] = {
            "index": track["index"].get() if isinstance(track["index"], tk.IntVar) else track["index"],
            "volume": track["volume"].get() if isinstance(track["volume"], tk.DoubleVar) else track["volume"],
            "pan": track["pan"].get() if isinstance(track["pan"], tk.DoubleVar) else track["pan"],
            "use_for_mixdown": track["use_for_mixdown"].get() if isinstance(track["use_for_mixdown"], tk.BooleanVar) else track["use_for_mixdown"],
        }
    save_mix_config(mix_config)


def mix_to_stereo():
    """Run the stereo mixdown for every loaded file, showing a progress dialog."""
    update_mix_config()

    global file_paths

    # ── Progress dialog ──────────────────────────────────────────────────────
    dlg = ctk.CTkToplevel(root)
    dlg.title("Mixdown Progress")
    dlg.geometry("420x130")
    dlg.attributes("-topmost", True)
    dlg.resizable(False, False)

    ctk.CTkLabel(dlg, text="Processing files …", font=ctk.CTkFont(size=13)).pack(pady=(18, 4))
    progress_bar = ctk.CTkProgressBar(dlg, width=360, mode="determinate")
    progress_bar.set(0)
    progress_bar.pack(pady=4)
    progress_lbl = ctk.CTkLabel(dlg, text="0.0 % — calculating …", font=ctk.CTkFont(size=11))
    progress_lbl.pack(pady=4)

    file_sizes = [os.path.getsize(f) / (1024 ** 3) for f in file_paths]
    estimated_total_time = sum(file_sizes) * 15           # ~15 s per GB
    start_time = datetime.now()
    dlg.update()

    for i, ifname in enumerate(file_paths):
        print(f"Processing: {ifname}")
        start_time_file = datetime.now()
        filesize = os.path.getsize(ifname) / (1024 ** 3)

        path, Outfilename = os.path.split(ifname)
        Outfilename, _ = os.path.splitext(Outfilename)

        if not output_folder.get():
            set_output_folder(path)

        data, samplerate = sf.read(ifname)

        active_tracks = [t for t in tracks if t["use_for_mixdown"].get()]
        if not active_tracks:
            print("No channels selected for mixdown!")
            dlg.destroy()
            return

        plain_active = [
            {"index": t["index"].get(), "volume": t["volume"].get(), "pan": t["pan"].get()}
            for t in active_tracks
        ]
        stereo = build_stereo_mix(data, plain_active)

        # Loudness normalisation
        if loudness_option.get() == "-1dBFS":
            print("Normalizing to -1 dBFS")
            stereo = pyln.normalize.peak(stereo, -1.0)
        elif loudness_option.get() == "-12dB LUFS":
            print("Normalizing to -12 dB LUFS")
            meter = pyln.Meter(samplerate)
            loudness = meter.integrated_loudness(stereo)
            print(f"Current loudness: {loudness} LUFS")
            stereo = pyln.normalize.loudness(stereo, loudness, -12.0)

        if output_folder.get():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_wav_path = "temp_stereo.wav"
            sf.write(temp_wav_path, stereo, samplerate)
            audio = AudioSegment.from_wav(temp_wav_path)
            audio = process_audio(audio, PHASE_DBFS_THRESH=3.25, SAMPLE_WIDTH=2,
                                   NORMALIZATION_HEADROOM=1, APPLY_FADE_LEN_THRESH_S=3,
                                   FADE_DURATION=80)
            y, sr = librosa.load(temp_wav_path)
            tempo = extract_bpm(y, sr)
            print(f"Estimated tempo: {tempo:.1f} BPM")

            loudness_abbrev = {"none": "none", "-1dBFS": "1dBFS", "-12dB LUFS": "12LUFS"}
            loudness_str = loudness_abbrev.get(loudness_option.get(), "none")
            tempo_str = f"{int(tempo)}BPM"
            fmt = output_format.get()
            out_path = os.path.join(
                output_folder.get(),
                f"{Outfilename}_{loudness_str}_{tempo_str}_{timestamp}.{fmt}"
            )
            audio.export(out_path, format=fmt)
            print(f"Stored as {fmt.upper()}: {out_path}")

            t = (datetime.now() - start_time_file).total_seconds()
            print(f"{t:.1f} s for {filesize:.3f} GB — {t/max(filesize, 0.001):.1f} s/GB")
        else:
            messagebox.showerror("Error", "No output folder selected!")

        # Update progress
        fraction = (i + 1) / len(file_paths)
        progress_bar.set(fraction)
        elapsed = (datetime.now() - start_time).total_seconds()
        remaining = max(estimated_total_time - elapsed, 0)
        progress_lbl.configure(
            text=f"{fraction * 100:.1f} % — {remaining:.0f} s remaining"
        )
        dlg.update()

    dlg.destroy()
    messagebox.showinfo("Success", "Mixdown completed successfully.")

    if os.name == "posix":
        os.system(f'open "{output_folder.get()}"')
    elif os.name == "nt":
        os.system(f'start "" "{output_folder.get()}"')




def preview_tracks():
    """Render a mini waveform for every track and add it as an extra column."""
    global file_paths
    if not file_paths:
        return

    data, _ = sf.read(file_paths[0])

    # Header for the preview column (col 8 — after the play button at col 7)
    ctk.CTkLabel(
        frame_controls, text="Waveform", width=220,
        font=ctk.CTkFont(size=12, weight="bold"), text_color=("gray60", "gray50")
    ).grid(row=0, column=8, padx=(8, 4), pady=(6, 4))

    for i, track in enumerate(tracks, start=1):
        idx = track["index"].get() - 1
        fig, ax = plt.subplots(figsize=(2.8, 0.32))
        fig.patch.set_facecolor("#1e1e1e")
        ax.set_facecolor("#1e1e1e")
        sample_points = np.linspace(0, len(data[:, idx]) - 1, min(1000, len(data)), dtype=int)
        ax.plot(data[sample_points, idx], color="#3b8ed0", linewidth=0.6)
        ax.axis("off")

        fig_canvas = FigureCanvasTkAgg(fig, master=frame_controls)
        fig_canvas.get_tk_widget().grid(row=i, column=8, padx=(8, 4), pady=2)
        fig_canvas.draw()
        plt.close(fig)


def set_output_folder(inFilePath=None):
    """Set the output directory, either from a path or via a folder picker."""
    if inFilePath and os.path.exists(inFilePath):
        folder_selected = inFilePath
    else:
        folder_selected = filedialog.askdirectory(initialdir=output_folder.get() or os.path.expanduser("~"))

    if folder_selected:
        output_folder.set(folder_selected)
        # Trim the displayed path if it's very long
        display = folder_selected if len(folder_selected) <= 60 else "…" + folder_selected[-57:]
        lbl_output_folder.configure(text=display)


# ─── Main window ───────────────────────────────────────────────────────────────
root = ctk.CTk()
root.title("Multichannel WAV Mixer")
root.geometry("1060x560")
root.minsize(900, 420)

def bring_to_front(event=None):
    root.attributes("-topmost", True)
    root.after(150, lambda: root.attributes("-topmost", False))

root.bind("<FocusIn>", bring_to_front)

# ─── State variables ───────────────────────────────────────────────────────────
file_paths: tuple = ()
tracks: list = []
output_folder = tk.StringVar(value="")
loudness_option = tk.StringVar(value="-1dBFS")
output_format = tk.StringVar(value="mp3")

# Cached PCM data for the first loaded file (used by track / mix preview)
_wav_data: np.ndarray | None = None
_wav_samplerate: int = 44_100

# The play button currently showing ■ (None when idle)
_active_play_btn = None

# ─── Toolbar ───────────────────────────────────────────────────────────────────
toolbar = ctk.CTkFrame(root, corner_radius=0, height=54, fg_color=("gray85", "gray15"))
toolbar.pack(side="top", fill="x")
toolbar.pack_propagate(False)

btn_load = ctk.CTkButton(
    toolbar, text="Load WAV", width=105, height=34,
    font=ctk.CTkFont(size=13), command=load_wav
)
btn_load.pack(side="left", padx=(12, 6), pady=10)

btn_preview = ctk.CTkButton(
    toolbar, text="Waveforms", width=100, height=34, state="disabled",
    font=ctk.CTkFont(size=13), command=preview_tracks,
    fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"), text_color=("gray20", "gray90")
)
btn_preview.pack(side="left", padx=6, pady=10)

btn_out = ctk.CTkButton(
    toolbar, text="Output Folder", width=120, height=34,
    font=ctk.CTkFont(size=13), command=set_output_folder,
    fg_color=("gray70", "gray30"), hover_color=("gray60", "gray40"), text_color=("gray20", "gray90")
)
btn_out.pack(side="left", padx=6, pady=10)

# Separator spacer
ctk.CTkLabel(toolbar, text="", width=10).pack(side="left")

# Loudness option menu
ctk.CTkLabel(
    toolbar, text="Loudness:", font=ctk.CTkFont(size=12),
    text_color=("gray40", "gray65")
).pack(side="left", padx=(6, 2), pady=10)
loudness_menu = ctk.CTkOptionMenu(
    toolbar, variable=loudness_option, width=120, height=34,
    values=["none", "-1dBFS", "-12dB LUFS"],
    font=ctk.CTkFont(size=12)
)
loudness_menu.pack(side="left", padx=(0, 6), pady=10)

# Output format segmented button
ctk.CTkLabel(
    toolbar, text="Format:", font=ctk.CTkFont(size=12),
    text_color=("gray40", "gray65")
).pack(side="left", padx=(10, 2), pady=10)
fmt_btn = ctk.CTkSegmentedButton(
    toolbar, values=["MP3", "WAV"], height=34,
    font=ctk.CTkFont(size=12),
    command=lambda v: output_format.set(v.lower())
)
fmt_btn.set("MP3")
fmt_btn.pack(side="left", padx=(0, 10), pady=10)

# Mix button (rightmost)
btn_mix = ctk.CTkButton(
    toolbar, text="Mix to Stereo ▶", width=140, height=34,
    font=ctk.CTkFont(size=13, weight="bold"), command=mix_to_stereo,
    fg_color="#2d7dd2", hover_color="#1a5fa8"
)
btn_mix.pack(side="right", padx=(6, 14), pady=10)

# Listen Mix button (left of Mix to Stereo)
btn_listen_mix = ctk.CTkButton(
    toolbar, text="Listen Mix \u25b6", width=130, height=34, state="disabled",
    font=ctk.CTkFont(size=13), command=preview_mix,
    fg_color="#2d8a4e", hover_color="#1f6438",
)
btn_listen_mix.pack(side="right", padx=(0, 6), pady=10)

# ─── Status bar (output path) ──────────────────────────────────────────────────
status_bar = ctk.CTkFrame(root, corner_radius=0, height=28, fg_color=("gray80", "gray12"))
status_bar.pack(side="bottom", fill="x")
status_bar.pack_propagate(False)

ctk.CTkLabel(
    status_bar, text="Output:", font=ctk.CTkFont(size=11),
    text_color=("gray40", "gray60"), width=52
).pack(side="left", padx=(10, 2))
lbl_output_folder = ctk.CTkLabel(
    status_bar, text="No folder selected", font=ctk.CTkFont(size=11),
    text_color=("gray30", "gray70"), anchor="w"
)
lbl_output_folder.pack(side="left", fill="x", expand=True)

# ─── Scrollable track area ─────────────────────────────────────────────────────
frame_controls = ctk.CTkScrollableFrame(
    root, corner_radius=0,
    fg_color=("gray97", "gray13"),
    scrollbar_button_color=("gray70", "gray35"),
    scrollbar_button_hover_color=("gray55", "gray50")
)
frame_controls.pack(fill="both", expand=True)

# ─── Run ───────────────────────────────────────────────────────────────────────
root.mainloop()
