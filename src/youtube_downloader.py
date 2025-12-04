"""
YouTube downloader module using yt-dlp.
"""
import os
import datetime
import subprocess
import shutil
import yt_dlp
from typing import Optional, Tuple, Generator, BinaryIO
from config.logger import get_logger
from config.settings import *
from src.models import VideoInfo, MediaFile

logger = get_logger(__name__)


class YouTubeDownloader:
    """Handles downloading videos and audio from YouTube."""

    def __init__(self, output_dir: str = None):
        """
        Initialize the downloader.

        Args:
            output_dir: Directory where to save downloaded files
        """
        self.output_dir = output_dir or TEMP_DOWNLOAD_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    def _build_yt_opts(
        self,
        outtmpl: str = None,
        want_video: bool = False,
        want_audio: bool = False,
        prefer_mp4: bool = True,
        quiet: bool = True
    ) -> dict:
        """
        Build yt-dlp options avoiding SABR and problematic web players.

        Args:
            outtmpl: Output template for filename
            want_video: Download video
            want_audio: Download audio only
            prefer_mp4: Prefer MP4 format for video
            quiet: Quiet mode

        Returns:
            dict: yt-dlp options dictionary
        """
        extractor_args = {
            "youtube": {
                "player_skip": YT_DLP_PLAYER_SKIP,
                "player_client": YT_DLP_PLAYER_CLIENT,
            }
        }

        http_headers = {
            "User-Agent": YT_DLP_USER_AGENT,
            "Accept-Language": YT_DLP_ACCEPT_LANGUAGE,
        }

        ydl_opts = {
            "quiet": quiet,
            "nocheckcertificate": False,
            "extractor_args": extractor_args,
            "http_headers": http_headers,
            "retries": YT_DLP_RETRIES,
            "fragment_retries": YT_DLP_FRAGMENT_RETRIES,
            "concurrent_fragment_downloads": 1,
            "noprogress": quiet,
            "socket_timeout": YT_DLP_SOCKET_TIMEOUT,
            "force_ipv4": True,
        }

        if outtmpl:
            ydl_opts["outtmpl"] = outtmpl

        if want_video:
            if prefer_mp4:
                ydl_opts["format"] = "bv*[vcodec*=avc1]+ba[acodec*=mp4a]/b[ext=mp4]/b"
                ydl_opts["merge_output_format"] = "mp4"
            else:
                ydl_opts["format"] = "bv*+ba/b"
        elif want_audio:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": YT_DLP_AUDIO_CODEC,
                "preferredquality": YT_DLP_AUDIO_QUALITY,
            }]

        return ydl_opts

    def get_video_info(self, video_url: str) -> Optional[VideoInfo]:
        """
        Get video information using yt-dlp.

        Args:
            video_url: YouTube video URL

        Returns:
            VideoInfo object or None if fails
        """
        ydl_opts = self._build_yt_opts(quiet=True)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                video_info = VideoInfo.from_yt_info(video_url, info)
                
                logger.info(f"📹 Video info: '{video_info.title}' ({video_info.upload_date})")
                logger.info(f"   ID: {video_info.video_id} | Channel: {video_info.channel}")
                logger.info(f"   Duration: {video_info.duration/60:.1f} min | Availability: {video_info.availability}")
                
                return video_info
        except Exception as e:
            logger.error(f"❌ Error getting video info for {video_url}: {e}", exc_info=True)
            return None

    def download_video(self, video_info: VideoInfo) -> Optional[MediaFile]:
        """
        Download video as MP4 avoiding SABR and prioritizing AVC1+MP4A codecs.

        Args:
            video_info: VideoInfo object with video details

        Returns:
            MediaFile object or None if fails
        """
        filename_base = f"{video_info.upload_date} - {video_info.safe_title}"
        output_template = os.path.join(self.output_dir, f"{filename_base}.%(ext)s")

        ydl_opts = self._build_yt_opts(
            outtmpl=output_template,
            want_video=True,
            prefer_mp4=True,
            quiet=True
        )

        try:
            logger.info(f"⬇️ Downloading video: {video_info.url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(video_info.url, download=True)

            # Find downloaded file
            for ext in ["mp4", "mkv", "webm", "avi", "mov"]:
                potential_path = os.path.join(self.output_dir, f"{filename_base}.{ext}")
                if os.path.exists(potential_path):
                    if ext != "mp4":
                        new_path = os.path.join(self.output_dir, f"{filename_base}.mp4")
                        os.rename(potential_path, new_path)
                        potential_path = new_path
                        logger.info(f"ℹ️ Video renamed to {os.path.basename(potential_path)}")

                    logger.info(f"✅ Video downloaded: {os.path.basename(potential_path)}")
                    return MediaFile(
                        path=potential_path,
                        filename=os.path.basename(potential_path),
                        file_type='video'
                    )

            logger.warning(f"⚠️ Could not find downloaded video file for {video_info.url}")
            return None

        except Exception as e:
            logger.error(f"❌ Error downloading video {video_info.url}: {e}", exc_info=True)
            return None

    def download_audio(self, video_info: VideoInfo) -> Optional[MediaFile]:
        """
        Download audio as MP3.

        Args:
            video_info: VideoInfo object with video details

        Returns:
            MediaFile object or None if fails
        """
        filename_base = f"{video_info.upload_date} - {video_info.safe_title}"
        output_template = os.path.join(self.output_dir, f"{filename_base}.%(ext)s")

        ydl_opts = self._build_yt_opts(
            outtmpl=output_template,
            want_audio=True,
            quiet=True
        )

        try:
            logger.info(f"🎵 Downloading audio: {video_info.url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(video_info.url, download=True)

            potential_path = os.path.join(self.output_dir, f"{filename_base}.mp3")

            if os.path.exists(potential_path):
                logger.info(f"✅ Audio downloaded: {os.path.basename(potential_path)}")
                return MediaFile(
                    path=potential_path,
                    filename=os.path.basename(potential_path),
                    file_type='audio'
                )
            else:
                logger.warning(f"⚠️ Could not find downloaded audio file for {video_info.url}")
                return None

        except Exception as e:
            logger.error(f"❌ Error downloading audio {video_info.url}: {e}", exc_info=True)
            return None

    def stream_and_capture(
        self,
        video_info: VideoInfo,
        save_video: bool = True
    ) -> Tuple[Optional[subprocess.Popen], Optional[BinaryIO], Optional[str]]:
        """
        Stream video from YouTube while simultaneously:
        1. Saving the video (MKV) to disk for backup
        2. Piping audio (WAV 16kHz mono) to stdout for real-time transcription

        Architecture: yt-dlp -> FFmpeg (multiple outputs)
        - Output 1: MKV file on disk (video + audio, copy codec)
        - Output 2: WAV audio stream to pipe (16kHz mono for Whisper)

        Args:
            video_info: VideoInfo object with video details
            save_video: Whether to save the video file to disk

        Returns:
            Tuple of (ffmpeg_process, audio_pipe, video_path)
            - ffmpeg_process: The subprocess.Popen object (for management)
            - audio_pipe: File-like object to read WAV audio from
            - video_path: Path to the saved MKV file (or None if save_video=False)
        """
        filename_base = f"{video_info.upload_date} - {video_info.safe_title}"
        video_path = os.path.join(self.output_dir, f"{filename_base}.mkv") if save_video else None

        # Build yt-dlp command to output to stdout
        # Using best format with video+audio for the saved file
        yt_dlp_cmd = [
            "yt-dlp",
            "--quiet",
            "--no-warnings",
            "-f", "bv*+ba/b",  # Best video + best audio, or best combined
            "-o", "-",  # Output to stdout
            "--no-part",
            "--retries", str(YT_DLP_RETRIES),
            "--fragment-retries", str(YT_DLP_FRAGMENT_RETRIES),
            "--socket-timeout", str(YT_DLP_SOCKET_TIMEOUT),
            "--force-ipv4",
            "--extractor-args", "youtube:player_client=android,ios,tv;player_skip=web_safari,web",
            "--user-agent", YT_DLP_USER_AGENT,
            video_info.url
        ]

        # Build FFmpeg command with multiple outputs
        # Input: pipe from yt-dlp
        # Output 1: MKV file (copy codecs, preserves quality)
        # Output 2: WAV audio to stdout (16kHz mono for Whisper)
        ffmpeg_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        ffmpeg_cmd.extend(["-i", "pipe:0"])  # Input from stdin

        if save_video and video_path:
            # Output 1: Save video file (copy codecs for speed)
            ffmpeg_cmd.extend([
                "-map", "0:v?",  # Video stream (optional, ? means don't fail if missing)
                "-map", "0:a?",  # Audio stream (optional)
                "-c", "copy",    # Copy codecs (no re-encoding)
                "-f", "matroska",
                video_path
            ])

        # Output 2: Audio stream for transcription (always)
        ffmpeg_cmd.extend([
            "-map", "0:a:0",           # First audio stream
            "-ar", str(STREAMING_SAMPLE_RATE),  # 16000 Hz for Whisper
            "-ac", "1",                # Mono
            "-f", "wav",               # WAV format
            "-acodec", "pcm_s16le",    # 16-bit PCM
            "pipe:1"                   # Output to stdout
        ])

        try:
            logger.info(f"🔴 Starting live stream capture: {video_info.url}")
            logger.info(f"   Video will be saved to: {video_path}")
            logger.info(f"   Audio streaming at {STREAMING_SAMPLE_RATE}Hz mono for transcription")

            # Start yt-dlp process (outputs to pipe)
            yt_dlp_process = subprocess.Popen(
                yt_dlp_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=STREAMING_BUFFER_SIZE
            )

            # Start FFmpeg process (reads from yt-dlp, outputs video to file + audio to pipe)
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=yt_dlp_process.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=STREAMING_BUFFER_SIZE
            )

            # Allow yt-dlp to receive SIGPIPE if ffmpeg exits
            yt_dlp_process.stdout.close()

            # Store yt-dlp process reference for cleanup
            ffmpeg_process._yt_dlp_process = yt_dlp_process

            logger.info("✅ Stream pipeline started successfully")
            return ffmpeg_process, ffmpeg_process.stdout, video_path

        except FileNotFoundError as e:
            missing_cmd = "yt-dlp" if "yt-dlp" in str(e) else "ffmpeg"
            logger.error(f"❌ {missing_cmd} not found. Please install it.")
            return None, None, None
        except Exception as e:
            logger.error(f"❌ Error starting stream pipeline: {e}", exc_info=True)
            return None, None, None

    def stop_stream(self, process: subprocess.Popen) -> bool:
        """
        Gracefully stop a streaming process and its associated yt-dlp process.

        Args:
            process: The FFmpeg subprocess.Popen object

        Returns:
            bool: True if stopped successfully
        """
        try:
            # Stop yt-dlp process if attached
            if hasattr(process, '_yt_dlp_process'):
                yt_dlp_proc = process._yt_dlp_process
                if yt_dlp_proc.poll() is None:
                    yt_dlp_proc.terminate()
                    try:
                        yt_dlp_proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        yt_dlp_proc.kill()
                        yt_dlp_proc.wait()

            # Stop FFmpeg process
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

            logger.info("✅ Stream processes stopped gracefully")
            return True

        except Exception as e:
            logger.error(f"❌ Error stopping stream: {e}", exc_info=True)
            return False

    def is_stream_active(self, process: subprocess.Popen) -> bool:
        """
        Check if the streaming process is still active.

        Args:
            process: The FFmpeg subprocess.Popen object

        Returns:
            bool: True if stream is still active
        """
        return process is not None and process.poll() is None

    def get_stream_errors(self, process: subprocess.Popen) -> str:
        """
        Get any error messages from the FFmpeg process.

        Args:
            process: The FFmpeg subprocess.Popen object

        Returns:
            str: Error messages or empty string
        """
        if process and process.stderr:
            try:
                # Non-blocking read
                import select
                if select.select([process.stderr], [], [], 0)[0]:
                    return process.stderr.read().decode('utf-8', errors='replace')
            except Exception:
                pass
        return ""
