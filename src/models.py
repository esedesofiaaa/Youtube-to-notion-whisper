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
    output_path: Optional[str] = None

    def save(self, output_path: str) -> str:
        """Save the transcription to a file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.text.strip())
        self.output_path = output_path
        return output_path


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
