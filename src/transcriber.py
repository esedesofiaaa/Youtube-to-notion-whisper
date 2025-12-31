"""
Audio transcription module using Faster-Whisper.
"""
import os
import io
import tempfile
import numpy as np
from typing import Optional, Generator, BinaryIO, Tuple, List
from faster_whisper import WhisperModel
from config.logger import get_logger
from config.settings import *
from src.models import MediaFile, TranscriptionResult, StreamingTranscriptionResult

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
                segments=segments_list,
                duration=info.duration
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

    def transcribe_stream(
        self,
        audio_pipe: BinaryIO,
        language: str = None,
        chunk_duration: float = None,
        on_chunk_callback: callable = None
    ) -> Generator[Tuple[str, List[dict]], None, StreamingTranscriptionResult]:
        """
        Transcribe audio from a streaming pipe in real-time.

        This method reads WAV audio data from a pipe, buffers it into chunks,
        and transcribes each chunk as it becomes available. It yields partial
        results and returns the complete transcription at the end.

        Args:
            audio_pipe: File-like object (pipe) providing WAV audio data
            language: ISO language code (optional, None for auto-detection)
            chunk_duration: Duration of each chunk in seconds (default from settings)
            on_chunk_callback: Optional callback function(text, segments) called for each chunk

        Yields:
            Tuple of (chunk_text, chunk_segments) for each transcribed chunk

        Returns:
            StreamingTranscriptionResult with complete transcription
        """
        chunk_duration = chunk_duration or STREAMING_CHUNK_DURATION
        sample_rate = STREAMING_SAMPLE_RATE
        bytes_per_sample = 2  # 16-bit PCM = 2 bytes per sample
        bytes_per_second = sample_rate * bytes_per_sample
        chunk_size_bytes = int(chunk_duration * bytes_per_second)

        logger.info(f"🔴 Starting streaming transcription")
        logger.info(f"   Chunk duration: {chunk_duration}s ({chunk_size_bytes} bytes)")
        logger.info(f"   Sample rate: {sample_rate}Hz")

        # Skip WAV header (44 bytes for standard WAV)
        try:
            wav_header = audio_pipe.read(44)
            if len(wav_header) < 44:
                logger.error("❌ Failed to read WAV header from stream")
                return StreamingTranscriptionResult(
                    text="",
                    language=language or "unknown",
                    language_probability=0.0,
                    segments=[],
                    chunks_processed=0,
                    stream_completed=False
                )
        except Exception as e:
            logger.error(f"❌ Error reading WAV header: {e}")
            return StreamingTranscriptionResult(
                text="",
                language=language or "unknown",
                language_probability=0.0,
                segments=[],
                chunks_processed=0,
                stream_completed=False
            )

        # Accumulators
        all_text = ""
        all_segments = []
        chunks_processed = 0
        detected_language = language
        language_probability = 0.0
        audio_buffer = b""
        time_offset = 0.0

        logger.info("=" * 80)
        logger.info("📝 LIVE STREAMING TRANSCRIPTION:")
        logger.info("=" * 80)

        try:
            while True:
                # Read audio data in smaller increments for responsiveness
                read_size = min(chunk_size_bytes - len(audio_buffer), STREAMING_BUFFER_SIZE)
                chunk_data = audio_pipe.read(read_size)

                if not chunk_data:
                    # End of stream - process remaining buffer if any
                    if len(audio_buffer) >= int(STREAMING_MIN_AUDIO_DURATION * bytes_per_second):
                        text, segments = self._transcribe_audio_buffer(
                            audio_buffer, sample_rate, detected_language, time_offset
                        )
                        if text:
                            all_text += text
                            all_segments.extend(segments)
                            chunks_processed += 1
                            logger.info(f"[FINAL] {text}")
                            if on_chunk_callback:
                                on_chunk_callback(text, segments)
                            yield (text, segments)
                    break

                audio_buffer += chunk_data

                # Process when buffer reaches chunk size
                if len(audio_buffer) >= chunk_size_bytes:
                    text, segments = self._transcribe_audio_buffer(
                        audio_buffer[:chunk_size_bytes], sample_rate, detected_language, time_offset
                    )

                    if text:
                        all_text += text
                        all_segments.extend(segments)
                        chunks_processed += 1

                        # Update detected language from first successful transcription
                        if not detected_language and segments:
                            detected_language = language or "en"

                        logger.info(f"[{chunks_processed}] {text}")
                        if on_chunk_callback:
                            on_chunk_callback(text, segments)
                        yield (text, segments)

                    # Update time offset and clear processed buffer
                    time_offset += chunk_duration
                    audio_buffer = audio_buffer[chunk_size_bytes:]

        except BrokenPipeError:
            logger.warning("⚠️ Stream pipe broken - processing remaining audio")
        except Exception as e:
            logger.error(f"❌ Error during streaming transcription: {e}", exc_info=True)

        logger.info("=" * 80)
        logger.info(f"✅ Streaming transcription complete: {chunks_processed} chunks processed")

        return StreamingTranscriptionResult(
            text=all_text.strip(),
            language=detected_language or "unknown",
            language_probability=language_probability,
            segments=all_segments,
            chunks_processed=chunks_processed,
            stream_completed=True
        )

    def _transcribe_audio_buffer(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        language: str = None,
        time_offset: float = 0.0
    ) -> Tuple[str, List[dict]]:
        """
        Transcribe a buffer of raw PCM audio data.

        Args:
            audio_bytes: Raw PCM audio bytes (16-bit signed, mono)
            sample_rate: Sample rate of the audio
            language: Language code (optional)
            time_offset: Time offset to add to segment timestamps

        Returns:
            Tuple of (transcribed_text, segments_list)
        """
        try:
            # Convert bytes to numpy array (16-bit signed integers)
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

            # Normalize to float32 in range [-1, 1] (required by Whisper)
            audio_float = audio_array.astype(np.float32) / 32768.0

            # Transcribe using faster-whisper
            # Note: faster-whisper can accept numpy arrays directly
            segments, info = self.model.transcribe(
                audio_float,
                language=language,
                **WHISPER_PARAMS
            )

            # Collect segments with adjusted timestamps
            text = ""
            segments_list = []
            for segment in segments:
                text += segment.text
                segments_list.append({
                    'start': segment.start + time_offset,
                    'end': segment.end + time_offset,
                    'text': segment.text
                })

            return text, segments_list

        except Exception as e:
            logger.error(f"❌ Error transcribing audio buffer: {e}", exc_info=True)
            return "", []

    def transcribe_stream_to_result(
        self,
        audio_pipe: BinaryIO,
        language: str = None
    ) -> StreamingTranscriptionResult:
        """
        Convenience method to transcribe a stream and collect all results.

        This method consumes the generator and returns the final result.
        Use transcribe_stream() directly if you need real-time updates.

        Args:
            audio_pipe: File-like object (pipe) providing WAV audio data
            language: ISO language code (optional)

        Returns:
            StreamingTranscriptionResult with complete transcription
        """
        generator = self.transcribe_stream(audio_pipe, language)

        # Consume all yielded chunks
        result = None
        try:
            while True:
                next(generator)
        except StopIteration as e:
            result = e.value

        return result or StreamingTranscriptionResult(
            text="",
            language=language or "unknown",
            language_probability=0.0,
            segments=[],
            chunks_processed=0,
            stream_completed=False
        )
