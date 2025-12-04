"""
Data models for YouTube to Google Drive automation.
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class VideoInfo:
    """Information about a YouTube video."""
    url: str
    title: str
    upload_date: str
    safe_title: str  # Sanitized title for file names

    @classmethod
    def from_url(cls, url: str, title: str, upload_date: str):
        """Create an instance from basic data."""
        from utils.helpers import sanitize_filename
        safe_title = sanitize_filename(title)
        return cls(
            url=url,
            title=title,
            upload_date=upload_date,
            safe_title=safe_title
        )


@dataclass
class MediaFile:
    """Represents a media file (video/audio)."""
    path: str
    filename: str
    file_type: str  # 'video', 'audio', 'transcription', 'link'

    def exists(self) -> bool:
        """Check if the file exists in the system."""
        import os
        return os.path.exists(self.path)

    def get_basename(self) -> str:
        """Return the base name of the file."""
        import os
        return os.path.basename(self.path)


@dataclass
class TranscriptionResult:
    """Result of an audio transcription."""
    text: str
    language: str
    language_probability: float
    segments: Optional[list] = None  # Segments with timestamps for SRT
    output_path: Optional[str] = None
    srt_path: Optional[str] = None

    def save(self, output_path: str) -> str:
        """Save the transcription to a file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.text.strip())
        self.output_path = output_path
        return output_path

    def save_srt(self, srt_path: str) -> str:
        """Save the transcription as SRT format."""
        if not self.segments:
            raise ValueError("No segments available to generate SRT")
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(self.segments, start=1):
                # SRT format:
                # 1
                # 00:00:00,000 --> 00:00:05,000
                # Text here
                
                start_time = self._format_timestamp(segment['start'])
                end_time = self._format_timestamp(segment['end'])
                text = segment['text'].strip()
                
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
        
        self.srt_path = srt_path
        return srt_path
    
    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


@dataclass
class StreamingTranscriptionResult:
    """Result of a streaming audio transcription."""
    text: str
    language: str
    language_probability: float
    segments: Optional[list] = None  # Segments with timestamps for SRT
    chunks_processed: int = 0  # Number of audio chunks processed
    stream_completed: bool = False  # Whether the stream finished successfully
    output_path: Optional[str] = None
    srt_path: Optional[str] = None

    def save(self, output_path: str) -> str:
        """Save the transcription to a file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.text.strip())
        self.output_path = output_path
        return output_path

    def save_srt(self, srt_path: str) -> str:
        """Save the transcription as SRT format."""
        if not self.segments:
            raise ValueError("No segments available to generate SRT")
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(self.segments, start=1):
                start_time = self._format_timestamp(segment['start'])
                end_time = self._format_timestamp(segment['end'])
                text = segment['text'].strip()
                
                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{text}\n\n")
        
        self.srt_path = srt_path
        return srt_path

    def _format_timestamp(self, seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def to_transcription_result(self) -> 'TranscriptionResult':
        """Convert to a standard TranscriptionResult for compatibility."""
        return TranscriptionResult(
            text=self.text,
            language=self.language,
            language_probability=self.language_probability,
            segments=self.segments,
            output_path=self.output_path,
            srt_path=self.srt_path
        )


@dataclass
class DriveFile:
    """Represents a file in Google Drive."""
    id: str
    name: str
    mime_type: Optional[str] = None
    parent_folder_id: Optional[str] = None

    @classmethod
    def from_api_response(cls, response: dict):
        """Create an instance from API response."""
        return cls(
            id=response.get('id'),
            name=response.get('name'),
            mime_type=response.get('mimeType'),
            parent_folder_id=response.get('parents', [None])[0] if response.get('parents') else None
        )


@dataclass
class ProcessingStatus:
    """Status of video processing."""
    video_info: VideoInfo
    video_downloaded: bool = False
    audio_downloaded: bool = False
    transcription_completed: bool = False
    drive_folder_created: bool = False
    video_uploaded: bool = False
    audio_uploaded: bool = False
    transcription_uploaded: bool = False
    link_uploaded: bool = False

    def is_complete(self) -> bool:
        """Check if processing is complete."""
        return all([
            self.video_downloaded,
            self.audio_downloaded,
            self.transcription_completed,
            self.drive_folder_created,
            self.video_uploaded,
            self.audio_uploaded,
            self.transcription_uploaded,
            self.link_uploaded
        ])

    def get_progress_percentage(self) -> float:
        """Calculate the progress percentage."""
        total_steps = 8
        completed_steps = sum([
            self.video_downloaded,
            self.audio_downloaded,
            self.transcription_completed,
            self.drive_folder_created,
            self.video_uploaded,
            self.audio_uploaded,
            self.transcription_uploaded,
            self.link_uploaded
        ])
        return (completed_steps / total_steps) * 100
