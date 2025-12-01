"""
Audio transcription module using Faster-Whisper.
"""
import os
from typing import Optional
from faster_whisper import WhisperModel
from config.logger import get_logger
from config.settings import *
from src.models import MediaFile, TranscriptionResult

logger = get_logger(__name__)


class AudioTranscriber:
    """Handles audio transcription using Faster-Whisper."""

    def __init__(self, model_name: str = None, device: str = None, compute_type: str = None):
        """
        Initialize the transcriber with a Whisper model.

        Args:
            model_name: Name of Whisper model (tiny, base, small, medium, large)
            device: Device to use ('cpu' or 'cuda')
            compute_type: Compute type ('int8', 'float16', etc.)
        """
        self.model_name = model_name or WHISPER_MODEL_DEFAULT
        self.device = device or WHISPER_DEVICE
        self.compute_type = compute_type or WHISPER_COMPUTE_TYPE

        logger.info(f"ℹ️ Loading Whisper model '{self.model_name}' on {self.device.upper()}...")
        if self.device == "cpu":
            logger.info("ℹ️ To use GPU: export WHISPER_DEVICE=cuda")

        self.model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type
        )
        logger.info(f"✅ Whisper model '{self.model_name}' loaded on {self.device.upper()}.")

    def transcribe(
        self,
        audio_file: MediaFile,
        language: str = None,
        output_path: str = None
    ) -> Optional[TranscriptionResult]:
        """
        Transcribe an audio file and save the result.

        Args:
            audio_file: MediaFile object with audio file info
            language: ISO language code (e.g. 'es', 'en', 'fr', None for auto-detection)
            output_path: Path where to save transcription

        Returns:
            TranscriptionResult object or None if fails
        """
        if not audio_file.exists():
            logger.error(f"❌ Audio file does not exist: {audio_file.path}")
            return None

        try:
            logger.info(f"🎤 Starting transcription: {audio_file.filename}")

            if language:
                logger.info(f"ℹ️ Language manually selected: {language}")
            else:
                logger.info("ℹ️ Automatic language detection activated")

            logger.info(f"ℹ️ Processing audio. Optimizing to avoid repetitions...")

            # Transcribe using faster-whisper
            segments, info = self.model.transcribe(
                audio_file.path,
                language=language,
                **WHISPER_PARAMS
            )

            logger.info(f"ℹ️ Detected language: {info.language} (probability: {info.language_probability:.2f})")
            logger.info("=" * 80)
            logger.info("📝 LIVE TRANSCRIPTION:")
            logger.info("=" * 80)

            # Collect all segments showing in real-time
            transcription_text = ""
            segments_list = []
            for segment in segments:
                logger.info(segment.text)
                transcription_text += segment.text
                # Store segment with timestamps for SRT generation
                segments_list.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text
                })

            logger.info("=" * 80)

            # Create transcription result
            result = TranscriptionResult(
                text=transcription_text,
                language=info.language,
                language_probability=info.language_probability,
                segments=segments_list
            )

            # Save if output path provided
            if output_path:
                result.save(output_path)
                logger.info(f"✅ Transcription saved: {os.path.basename(output_path)}")

            return result

        except Exception as e:
            logger.error(f"❌ Error during transcription of {audio_file.filename}: {e}", exc_info=True)
            return None

    def transcribe_file(
        self,
        audio_path: str,
        output_path: str,
        language: str = None
    ) -> Optional[str]:
        """
        Convenience method to transcribe a file by path.

        Args:
            audio_path: Path to audio file
            output_path: Path where to save transcription
            language: ISO language code (optional)

        Returns:
            Path to transcription file or None if fails
        """
        audio_file = MediaFile(
            path=audio_path,
            filename=os.path.basename(audio_path),
            file_type='audio'
        )

        result = self.transcribe(audio_file, language, output_path)
        return result.output_path if result else None
