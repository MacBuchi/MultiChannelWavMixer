# MultiChannelWavMixer
Simple Downmix tool for Multichannel WV files compatible to RME Durec format

For installation Python environment is required. Use requirements.txt to install all dependencies.

## Description

`MultiChannelWavMixer.py` is a Python script designed to downmix multichannel WAV files into stereo or other channel configurations. It is particularly compatible with the RME Durec format, making it suitable for audio professionals who need to process recordings from RME audio interfaces.

### Installation
```sh
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
```

### Features

- Downmix multichannel WAV files to stereo based on custom channel configurations.
- Compatible with RME Durec format.
- Supports batch processing of multiple files.
- Customizable downmix parameters.
- optional WAV or MP3 output
- Save Configuration in a config file (MixConf.json)

#### added 2025-02-09
  - add Loudness normalization feature with option -1dB Peak (default), -12dB LUFS and none (no normalization)

#### added 2025-02-05
  - double-click Volume slider >> set to 1.0
  - double-cklick Pan slider >> set to 0.5
  - Preview of audio channels using the first listed WAV file given



### Usage

To use `MultiChannelWavMixer.py`, run the script with the desired input and output file paths, along with any optional parameters for custom downmixing.

#### Example
```sh
python MultiChannelWavMixer.py
```

### GUI Layout

The GUI consists of the following elements:

- **Top Frame:**
  - Load WAV button
  - Preview button
  - Select output folder button
  - Toggle output format button
  - Mix to Stereo button
  - Loudness normalization dropdown menu

- **Bottom Frame:**
  - Output Path label
  - Output folder label

- **Frame Controls:**
  - Index entry
  - Mixdown checkbox
  - Name label
  - Volume slider
  - Pan slider


Rough preview of first WAV File helps to quickly identify the used tracks
![Preview Feature](doc/Preview.png)

### Structure
```mermaid
graph LR;
    A[Main GUI Window Initialization] --> B[Load WAV File]
    B --> C[Parse iXML Data]
    B --> D[Load Mix Configuration]
    B --> E[Update GUI with Track Information]
    B --> F[Enable Preview Button]
    A --> G[Mix to Stereo]
    G --> H[Update Mix Configuration]
    G --> I[Create Progress Bar Window]
    G --> J[Process Each WAV File]
    J --> K[Read Audio Data]
    J --> L[Mix Tracks to Stereo]
    J --> M[Apply Loudness Normalization]
    J --> N[Export Mixed Audio]
    G --> O[Open Output Folder]
    G --> P[Display Success Message]
    A --> Q[Preview Tracks]
    Q --> R[Display Audio Amplitude]
    A --> S[Helper Functions]
    S --> T[load_mix_config]
    S --> U[save_mix_config]
    S --> V[clean_xml]
    S --> W[parse_ixml]
    S --> X[update_mix_config]
    S --> Y[extract_bpm]
    S --> Z[process_audio]
```
