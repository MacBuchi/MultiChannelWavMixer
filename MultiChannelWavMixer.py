
import tkinter as tk
from tkinter import filedialog, ttk
import xml.etree.ElementTree as ET
import soundfile as sf
import numpy as np
import os
import re
import pydub
from pydub import AudioSegment
from datetime import datetime
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pyloudnorm as pyln

# Function to load the mix configuration from a JSON file
CONFIG_FILE = "MixConf.json"  # Constant for the MixConf file

def load_mix_config():
    """Loads the MixConf.json file and returns a dictionary with tkinter variables."""
    if not os.path.exists(CONFIG_FILE):
        return {}

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        try:
            raw_config = json.load(f)
        except json.JSONDecodeError:
            return {}

    # Convert standard values to tkinter variables
    mix_config = {}
    for name, values in raw_config.items():
        mix_config[name] = {
            "index": tk.IntVar(value=values.get("index", 0)),
            "volume": tk.DoubleVar(value=values.get("volume", 1.0)),
            "pan": tk.DoubleVar(value=values.get("pan", 0.5)),
            "use_for_mixdown": tk.BooleanVar(value=values.get("use_for_mixdown", True))
        }
    return mix_config

def save_mix_config(mix_config):
    """Saves the MixConf data to MixConf.json, extracting values from tkinter variables."""
    raw_config = {
        name: {
            "index": values["index"].get() if isinstance(values["index"], tk.IntVar) else values["index"],
            "volume": values["volume"].get() if isinstance(values["volume"], tk.DoubleVar) else values["volume"],
            "pan": values["pan"].get() if isinstance(values["pan"], tk.DoubleVar) else values["pan"],
            "use_for_mixdown": values["use_for_mixdown"].get() if isinstance(values["use_for_mixdown"], tk.BooleanVar) else values["use_for_mixdown"]
        }
        for name, values in mix_config.items()
    }

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(raw_config, f, indent=4)

def clean_xml(data):
    """Removes everything before the first '<?xml' and cleans non-printable characters."""
    start = data.find("<?xml")  # Find the start of the XML document
    if start != -1:
        data = data[start:]  # Cut off everything before '<?xml'
    else:
        print("Warning: No valid XML start found!")
        return ""

    data = re.sub(r'[^\x20-\x7E]+', '', data)  # Remove non-printable characters
    return data.strip()  # Remove leading and trailing whitespace

def parse_ixml(file_path):
    with open(file_path, "rb") as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b'\n':
            f.seek(-2, os.SEEK_CUR)
        ixml_data = f.readline().decode("utf-8", errors="ignore").strip()
    ixml_data = clean_xml(ixml_data)  # Clean the XML data

    if not ixml_data:
        print("Error: No valid iXML data extracted.")
        return []

    try:
        root = ET.fromstring(ixml_data)  # Validate XML
    except ET.ParseError as e:
        print("Error parsing iXML data:", e)
        return []

    tracks = []
    for track in root.findall(".//TRACK"):
        name = track.find("NAME").text if track.find("NAME") is not None else "Unknown"
        index = track.find("INTERLEAVE_INDEX").text if track.find("INTERLEAVE_INDEX") is not None else "0"
        tracks.append((index, name))

    tracks_dict = []
    for index, name in tracks:
        pan = 0.5  # Default value
        if name.endswith(" L"):
            pan = 0
        elif name.endswith(" R"):
            pan = 1
        
        # Here volume and pan are stored directly as tkinter variables!
        tracks_dict.append({
            'index': tk.IntVar(value=int(index)),
            'name': name,
            'volume': tk.DoubleVar(value=1.0),  
            'pan': tk.DoubleVar(value=pan),  
            'use_for_mixdown': tk.BooleanVar(value=True)
        })
    
    return tracks_dict

# def safe_open_file_dialog():
#     root = tk.Toplevel()
#     root.withdraw()  # Verstecke das Fenster
#     file_path = filedialog.askopenfilename(filetypes=[("WAV files", "*.wav")])
#     root.destroy()  # Schließe das Fenster nach Auswahl
#     return file_path

def load_wav():
    global file_paths
    file_paths = filedialog.askopenfilenames(filetypes=[("WAV files", "*.wav")])
    # file_paths = safe_open_file_dialog()
    if not file_paths:
        return  

    global tracks
    file_path = file_paths[0]
    tracks = parse_ixml(file_path)
    mix_config = load_mix_config()

    for track in tracks:
        name = track["name"]
        if name in mix_config:
            track.update(mix_config[name])  # Assign tkinter variables directly

    # Update GUI
    for widget in frame_controls.winfo_children():
        widget.destroy()

    header = ["Index", "Mixdown", "Name", "Volume", "Pan"]
    for col, text in enumerate(header):
        lbl = tk.Label(frame_controls, text=text, width=10, font=("Arial", 14, "bold"))
        lbl.grid(row=0, column=col, padx=5, pady=2)

    for i, track in enumerate(tracks, start=1):
        idx = tk.Entry(frame_controls, width=5, textvariable=track["index"])
        idx.grid(row=i, column=0, padx=5, pady=2)

        chk = tk.Checkbutton(frame_controls, variable=track["use_for_mixdown"])
        chk.grid(row=i, column=1, padx=5, pady=2)

        lbl = tk.Label(frame_controls, text=track["name"], width=20)
        lbl.grid(row=i, column=2, padx=5, pady=2)

        vol = tk.Scale(frame_controls, from_=0, to=2, resolution=0.01, orient=tk.HORIZONTAL, variable=track["volume"], length=100)
        vol.grid(row=i, column=3, padx=5, pady=2)
        
        def vol_set_to_default(event, scale=vol):
            scale.set(1.0)
        vol.bind("<Double-Button-1>", vol_set_to_default)

        pan = tk.Scale(frame_controls, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL, variable=track["pan"], length=100)
        pan.grid(row=i, column=4, padx=5, pady=2)

        def pan_set_to_default(event, scale=pan):
            scale.set(0.5)
        pan.bind("<Double-Button-1>", pan_set_to_default)

    frame_controls.update_idletasks()  # Update the GUI
    canvas.config(scrollregion=canvas.bbox("all"))  # Update the scroll region
    path = os.path.dirname(file_path)  # Get the directory of the file
    set_output_folder(path)  # Set the output folder to the directory of the file

    btn_preview.config(state=tk.NORMAL)  # Enable the Preview button

def update_mix_config():
    """Updates MixConf based on current GUI values."""
    mix_config = load_mix_config()
    for track in tracks:
        mix_config[track["name"]] = {
            "index": track["index"].get() if isinstance(track["index"], tk.IntVar) else track["index"],
            "volume": track["volume"].get() if isinstance(track["volume"], tk.DoubleVar) else track["volume"],
            "pan": track["pan"].get() if isinstance(track["pan"], tk.DoubleVar) else track["pan"],
            "use_for_mixdown": track["use_for_mixdown"].get() if isinstance(track["use_for_mixdown"], tk.BooleanVar) else track["use_for_mixdown"]
        }
    save_mix_config(mix_config)

def mix_to_stereo():
    """Creates a stereo file based on the GUI settings."""
    update_mix_config()  # Save MixConfig after mixdown

    global file_paths  # global variable for the file paths
    # New window for the progress bar
    progress_window = tk.Toplevel(root)
    progress_window.title("Progress")
    progress_window.geometry("400x100")
    progress_window.attributes('-topmost', True)
    progress = ttk.Progressbar(progress_window, orient="horizontal", length=300, mode="determinate")
    progress.pack(pady=10)
    progress["maximum"] = len(file_paths)
    progress["value"] = 0
    progress_label = tk.Label(progress_window, text="0 %")
    progress_label.pack(pady=5)
    file_sizes = [os.path.getsize(f) / (1024 ** 3) for f in file_paths]  # Convert to GB
    total_size = sum(file_sizes)
    estimated_total_time = total_size * 15  # 15 seconds per GB
    start_time = datetime.now()
    progress_label.config(text=f"{0:.1f} % - Remaining time: {estimated_total_time:.1f} seconds")
    progress_window.update()
    for i, ifname in enumerate(file_paths):
        print(f"processing: {ifname}")

        start_time_file = datetime.now()
        filesize = file_sizes[i]
        filesize = os.path.getsize(ifname) / (1024 ** 3)
        # Remaining code for mixing the files
        path, Outfilename = os.path.split(ifname)
        Outfilename, extension = os.path.splitext(Outfilename)
        if not output_folder.get():
            set_output_folder(path)
        data, samplerate = sf.read(ifname)

        active_tracks = [track for track in tracks if track["use_for_mixdown"].get()]

        if not active_tracks:
            print("No channels selected for mixdown!")
            return

        stereo = np.zeros((data.shape[0], 2))

        for track in active_tracks:
            idx = track["index"].get() - 1
            volume = track["volume"].get()
            pan = track["pan"].get()

            stereo[:, 0] += data[:, idx] * volume * (1 - pan)
            stereo[:, 1] += data[:, idx] * volume * pan

        if loudness_option.get() == "-1dBFS":
            print("Normalizing to -1 dBFS")
            stereo = pyln.normalize.peak(stereo, -1.0)
        elif loudness_option.get() == "-12dB LUFS":
            print("Normalizing to -12 dB LUFS")
            meter = pyln.Meter(samplerate) # create BS.1770 meter
            loudness = meter.integrated_loudness(stereo) # measure loudness
            print(f"Current loudness: {loudness} LUFS")
            stereo = pyln.normalize.loudness(stereo, loudness, -12.0)

        if output_folder.get():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            temp_wav_path = "temp_stereo.wav"
            sf.write(temp_wav_path, stereo, samplerate)

            audio = AudioSegment.from_wav(temp_wav_path)

            loudness_abbrev = {
                "none": "none",
                "-1dBFS": "1dBFS",
                "-12dB LUFS": "12LUFS"
            }
            loudness_str = loudness_abbrev.get(loudness_option.get(), "none")

            if output_format.get() == "mp3":
                out_path = os.path.join(output_folder.get(), f"{Outfilename}_{loudness_str}_{timestamp}.mp3")
                audio.export(out_path, format="mp3")
            else:
                out_path = os.path.join(output_folder.get(), f"{Outfilename}_{loudness_str}_{timestamp}.wav")
                audio.export(out_path, format="wav")

            os.remove(temp_wav_path)
            t = (datetime.now() - start_time_file).total_seconds()
            print(f"{t:.1f} seconds for {filesize:.1f} GB - {t/filesize:.1f} seconds per GB")
        else:
            tk.messagebox.showerror("Error", "Select output path!")
        progress["value"] = i + 1
        progress_percentage = (i + 1) / len(file_paths) * 100
        elapsed_time = (datetime.now() - start_time).total_seconds()
        estimated_remaining_time = max((estimated_total_time - elapsed_time), 0)
        progress_label.config(text=f"{progress_percentage:.1f} % - Remaining time: {estimated_remaining_time:.1f} seconds")
        progress_window.update()

    # Open folder in Finder
    if os.name == 'posix':
        os.system(f'open "{output_folder.get()}"')
    elif os.name == 'nt':
        os.system(f'start {output_folder.get()}"')

    progress_window.destroy()
    tk.messagebox.showinfo("Success", "Mixdown completed")

def preview_tracks():
    """Displays the audio amplitude for each track in a small figure."""
    global file_paths
    if not file_paths:
        return

    file_path = file_paths[0]
    data, samplerate = sf.read(file_path)


    # Preview Header
    lbl = tk.Label(frame_controls, text="Preview", width=10, font=("Arial", 14, "bold"))
    lbl.grid(row=0, column=5, padx=5, pady=2)

    for i, track in enumerate(tracks, start=1):
        idx = track["index"].get() - 1
        fig, ax = plt.subplots(figsize=(3, 0.35))  # Adjust the height to make the plots flatter
        sample_points = np.linspace(0, len(data[:, idx]) - 1, min(1000,len(data)), dtype=int)
        ax.plot(data[sample_points, idx])
        # ax.set_title(track["name"])
        ax.axis('off')

        canvas = FigureCanvasTkAgg(fig, master=frame_controls)
        canvas.get_tk_widget().grid(row=i, column=5, padx=5, pady=3)
        canvas.draw()

# Main GUI window
root = tk.Tk()
root.attributes('-topmost', True)
def bring_to_front(event):
    root.attributes('-topmost', True)
    root.attributes('-topmost', False)

root.bind("<FocusIn>", bring_to_front)
root.title("Multichannel WAV Mixer")
root.geometry("750x400")
root.configure(bg='#00b4d8')


top_frame = tk.Frame(root, bg='#00b4d8')
top_frame.pack(pady=2)
bottom_frame = tk.Frame(root, bg='#00b4d8')
bottom_frame.pack(pady=2)

btn_load = tk.Button(top_frame, text="Load WAV", command=load_wav)
btn_load.pack(side=tk.LEFT, padx=5)

btn_preview = tk.Button(top_frame, text="Preview", command=preview_tracks, state=tk.DISABLED)
btn_preview.pack(side=tk.LEFT, padx=5)

output_folder = tk.StringVar(value="")
def set_output_folder(inFilePath=None):
    if inFilePath and os.path.exists(inFilePath):
        folder_selected = inFilePath
    else:
        folder_selected = filedialog.askdirectory(initialdir=output_folder.get())
    
    if folder_selected:
        output_folder.set(folder_selected)

btn_out = tk.Button(top_frame, text="Select output folder", command=set_output_folder)
btn_out.pack(side=tk.LEFT, padx=5)

lbl_output_path = tk.Label(bottom_frame, text="Output Path:", bg='#00b4d8', fg='white')
lbl_output_path.pack(side=tk.LEFT, padx=5)

lbl_output_folder = tk.Label(bottom_frame, textvariable=output_folder, bg='#00b4d8', fg='white')
lbl_output_folder.pack(side=tk.LEFT, padx=5)



# Toggle button to select output format
output_format = tk.StringVar(value="mp3")

def toggle_format():
    if output_format.get() == "mp3":
        output_format.set("wav")
        btn_toggle_format.config(text=".wav", relief=tk.SUNKEN)
    else:
        output_format.set("mp3")
        btn_toggle_format.config(text=".mp3", relief=tk.RAISED)

btn_toggle_format = tk.Button(top_frame, text=".mp3", command=toggle_format)
btn_toggle_format.pack(side=tk.LEFT, padx=5)

btn_mix = tk.Button(top_frame, text="Mix to Stereo", command=mix_to_stereo)
btn_mix.pack(side=tk.RIGHT, padx=1)

# Dropdown for Loudness Optimization
loudness_option = tk.StringVar(value="-1dBFS") # Default value is -1dBFS for loudness normalization

def set_loudness_option(value):
    loudness_option.set(value)

loudness_menu = tk.OptionMenu(top_frame, loudness_option, "none", "-1dBFS", "-12dB LUFS")
loudness_menu.pack(side=tk.LEFT, padx=5)

frame_container = tk.Frame(root)
frame_container.pack(fill=tk.BOTH, expand=True)

canvas = tk.Canvas(frame_container, bg='#000000')  # Black background
canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = tk.Scrollbar(frame_container, orient=tk.VERTICAL, command=canvas.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

canvas.configure(yscrollcommand=scrollbar.set)

frame_controls = tk.Frame(canvas, bg='#000000')
canvas.create_window((0, 0), window=frame_controls, anchor="nw")

def on_mouse_wheel(event):
    if event.delta < 0:
        canvas.yview_scroll(1, "units")
    else:
        canvas.yview_scroll(-1, "units")

canvas.bind_all("<MouseWheel>", on_mouse_wheel)
canvas.bind_all("<Button-4>", on_mouse_wheel)
canvas.bind_all("<Button-5>", on_mouse_wheel)

root.mainloop()
