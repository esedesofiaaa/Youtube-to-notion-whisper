# YouTube to Google Drive Automation

Automated system to download YouTube videos, transcribe them with **Faster-Whisper**, and organize them in Google Drive.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [System Components](#system-components)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Overview

This system provides a complete solution to automate YouTube content processing:

- Automated video and audio download from YouTube
- AI-powered transcription with Faster-Whisper
- Organized storage in Google Drive
- Robust error handling system

The project is designed to process YouTube videos in a simple and efficient way.

## Key Features

### Video Processing

- **Optimized download** with `yt-dlp` and mobile client support (avoids SABR errors)
- **Flexible formats**: MP4 for video, MP3 for audio
- **Metadata extraction**: title, publish date, original URL
- **Name management**: automatic sanitization and `YYYY-MM-DD - Title` format

### Transcription with Faster-Whisper

#### Advantages over Classic OpenAI Whisper

| Feature | Faster-Whisper | OpenAI Whisper |
|---------|----------------|----------------|
| Python Compatibility | 3.10 - 3.14+ | 3.10 - 3.13 |
| CPU Speed | **2.67x faster** | Baseline |
| GPU Speed | **3-4x faster** | Baseline |
| VRAM Usage | **50% less (1GB)** | 2GB (medium) |
| Live Transcription | Yes | No |

#### Real Performance

| Hardware | 2h Video | Model | Optimization |
|----------|----------|-------|--------------|
| CPU (8 cores) | 45 min | medium | int8 |
| GPU RTX 3060 | 12-15 min | medium | float16 |
| GPU RTX 4090 | 8-10 min | medium | float16 |

### Google Drive Organization

- **Hierarchical structure**: folders by date and title
- **Duplicate prevention**: verification before upload
- **Complete files**: video, audio, transcription and original link
- **Shared drive support**: compatible with Google Workspace

## System Components

### Main Scripts

- **DiscordToDrive.py**: Main video processing (download, transcription and upload)
- **LocalTranscriber.py**: CLI tool for local transcription of existing files

### Workflow

1. **Input**: YouTube URLs in `LinksYT.json`
2. **Processing**: Video/audio download with yt-dlp
3. **Transcription**: Audio to text conversion with Faster-Whisper
4. **Output**: Organization in Google Drive by date and title

### Key Technologies

- **Python 3.10+**: Main language
- **Faster-Whisper**: Transcription engine with CTranslate2
- **yt-dlp**: Robust YouTube download
- **Google Drive API**: Cloud storage
- **FFmpeg**: Multimedia processing

## System Requirements

### Required Software

- **Python**: 3.10 or higher (3.14 fully supported)
- **FFmpeg**: For audio/video processing
- **Git**: To clone the repository

### Recommended Hardware

#### Minimum (CPU)
- Processor: 4+ cores
- RAM: 8 GB
- Storage: 20 GB free

#### Optimal (GPU)
- GPU: NVIDIA with 4+ GB VRAM
- CUDA: 11.8 or higher
- RAM: 16 GB
- Storage: 50 GB free (SSD recommended)

## Installation

### 1. Install FFmpeg

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update && sudo apt install ffmpeg
ffmpeg -version
```

**macOS**:
```bash
brew install ffmpeg
```

**Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### 2. Clone the Repository

```bash
git clone https://github.com/esedesofiaaa/Youtube-to-notion-whisper.git
cd Youtube-to-notion-whisper
```

### 3. Create Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

**For GPU (NVIDIA with CUDA)**:
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

## Configuration

### 1. Google Drive API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project and enable **Google Drive API**
3. Create **OAuth 2.0** credentials (Desktop Application)
4. Download JSON and save it as `credentials.json` in root
5. First run: browser will open for authorization (generates `token.pickle`)

### 2. `LinksYT.json` File

```json
{
  "parent_folder_id": "DRIVE_FOLDER_ID",
  "video_urls": [
    "https://www.youtube.com/watch?v=VIDEO_ID"
  ]
}
```

**Get folder ID**: Drive URL `https://drive.google.com/drive/folders/ID_HERE`

## Usage Guide

### Mode 1: YouTube Video Processing

```bash
# Verify files
ls credentials.json LinksYT.json

# Execute
python DiscordToDrive.py
```

**Expected output**:
```
Processing: https://www.youtube.com/watch?v=example
Folder '2025-11-15 - Title' created
Video downloaded: 2025-11-15 - Title.mp4
Audio downloaded: 2025-11-15 - Title.mp3
Starting transcription...
================================================================================
LIVE TRANSCRIPTION:
================================================================================
[Transcribed text appears here in real time...]
================================================================================
File uploaded to Drive
Processing complete.
```

### Mode 2: Local Transcription

```bash
# Copy files to input/
cp my_videos/*.mp4 input/

# Transcribe
python LocalTranscriber.py --lang en

# View results
ls output/
```

**Options**:
- `--lang en`: Specify language (es, en, fr, de, it, pt, etc.)
- `--input ./videos`: Custom input directory
- `--output ./texts`: Custom output directory

### GPU Usage

```bash
export WHISPER_DEVICE=cuda
python DiscordToDrive.py
```

**Comparison**:
- CPU (8 cores): 45 min for 2h video
- GPU RTX 3060: 12-15 min (3x faster)
- GPU RTX 4090: 8-10 min (5x faster)

## Component Details

### DiscordToDrive.py

Main script for download, transcription and upload to Google Drive.

**Available Whisper models**:

| Model | Speed | Accuracy | VRAM | RAM |
|-------|-------|----------|------|-----|
| tiny | Very fast | Low | 1GB | 1GB |
| base | Fast | Medium | 1GB | 1GB |
| small | Medium | Medium | 2GB | 2GB |
| medium | Slow | High | 5GB | 5GB |
| large | Very slow | Very high | 10GB | 10GB |

Change model in `DiscordToDrive.py` line ~170:
```python
whisper_model = WhisperModel("medium", device=device)
```

### LocalTranscriber.py

Standalone CLI tool for local transcription:
- Extracts audio from videos with FFmpeg
- Uses `medium` model by default
- Supports automatic language detection
- Processes multiple files in batch

## Troubleshooting

### FFmpeg not found

```bash
# Verify
ffmpeg -version

# Install
sudo apt install ffmpeg  # Linux
brew install ffmpeg      # macOS
```

### Google authentication error

```bash
# Regenerate token
rm token.pickle
python DiscordToDrive.py  # Browser will open
```

### CUDA out of memory

```python
# Option 1: Smaller model
whisper_model = WhisperModel("small", device=device)

# Option 2: Force CPU
export WHISPER_DEVICE=cpu
```

### yt-dlp SABR error

```bash
# Update yt-dlp
pip install --upgrade yt-dlp
```

### Transcription with repetitions

Already implemented in code with optimized parameters. If persists:

```python
# In transcribe_audio(), adjust:
temperature=0.0,  # More deterministic
no_speech_threshold=0.4  # More aggressive
```

## Technologies

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube download
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - AI transcription
- [Google Drive API](https://developers.google.com/drive) - Storage
- [FFmpeg](https://ffmpeg.org/) - Multimedia processing

## License

This project is open source. See the LICENSE file for more details.
