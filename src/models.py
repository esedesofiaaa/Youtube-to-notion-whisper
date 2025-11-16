"""
Data models for YouTube to Google Drive automation.
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class VideoInfo:
    """Información de un video de YouTube."""
    url: str
    title: str
    upload_date: str
    safe_title: str  # Título sanitizado para nombres de archivo

    @classmethod
    def from_url(cls, url: str, title: str, upload_date: str):
        """Crea una instancia desde datos básicos."""
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
    """Representa un archivo de medio (video/audio)."""
    path: str
    filename: str
    file_type: str  # 'video', 'audio', 'transcription', 'link'

    def exists(self) -> bool:
        """Verifica si el archivo existe en el sistema."""
        import os
        return os.path.exists(self.path)

    def get_basename(self) -> str:
        """Retorna el nombre base del archivo."""
        import os
        return os.path.basename(self.path)


@dataclass
class TranscriptionResult:
    """Resultado de una transcripción de audio."""
    text: str
    language: str
    language_probability: float
    output_path: Optional[str] = None

    def save(self, output_path: str) -> str:
        """Guarda la transcripción en un archivo."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(self.text.strip())
        self.output_path = output_path
        return output_path


@dataclass
class DriveFile:
    """Representa un archivo en Google Drive."""
    id: str
    name: str
    mime_type: Optional[str] = None
    parent_folder_id: Optional[str] = None

    @classmethod
    def from_api_response(cls, response: dict):
        """Crea una instancia desde respuesta de API."""
        return cls(
            id=response.get('id'),
            name=response.get('name'),
            mime_type=response.get('mimeType'),
            parent_folder_id=response.get('parents', [None])[0] if response.get('parents') else None
        )


@dataclass
class ProcessingStatus:
    """Estado del procesamiento de un video."""
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
        """Verifica si el procesamiento está completo."""
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
        """Calcula el porcentaje de progreso."""
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
