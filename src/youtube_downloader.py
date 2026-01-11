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
        Build yt-dlp options using cookie-based authentication.
        
        This configuration uses a cookies.txt file exported from a browser
        to authenticate with YouTube, combined with Android/iOS client 
        spoofing to avoid PO Token requirements on residential IPs.

        Args:
            outtmpl: Output template for filename
            want_video: Download video
            want_audio: Download audio only
            prefer_mp4: Prefer MP4 format for video
            quiet: Quiet mode

        Returns:
            dict: yt-dlp options dictionary
        """
        # Cookie file path (Netscape format exported from browser)
        cookiefile = os.path.join(os.getcwd(), "youtube.com_cookies.txt")
        
        # Extractor args: Force Android/iOS clients, skip web clients
        extractor_args = {
            "youtube": {
                "player_skip": YT_DLP_PLAYER_SKIP,
                "player_client": YT_DLP_PLAYER_CLIENT,
            }
        }

        # Android User-Agent header
        http_headers = {
            "User-Agent": YT_DLP_USER_AGENT,
            "Accept-Language": YT_DLP_ACCEPT_LANGUAGE,
        }

        ydl_opts = {
            # Cookie-based authentication
            "cookiefile": cookiefile,
            
            # Core options
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
                # Prioritize standard HD (1080p) - User request: "Standard HD"
                # Fallback chain: 
                # 1. Best video <= 1080p + Best audio (merged to mp4)
                # 2. Best file with mp4 extension <= 1080p
                ydl_opts["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
                ydl_opts["merge_output_format"] = "mp4"
            else:
                ydl_opts["format"] = "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
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
                logger.info(f"   Duration: {video_info.duration/60:.1f} min | Resolution: {video_info.resolution} | Availability: {video_info.availability}")
                
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
        save_video: bool = True,
        is_live: bool = False
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
            is_live: Whether the video is a live stream

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
            "--wait-for-video", "30-120",  # Wait for scheduled/premiering videos (30-120 seconds retry)
            "--retries", str(YT_DLP_RETRIES),
            "--fragment-retries", str(YT_DLP_FRAGMENT_RETRIES),
            "--socket-timeout", str(YT_DLP_SOCKET_TIMEOUT),
            "--force-ipv4",
            "--extractor-args", "youtube:player_client=android,ios,tv;player_skip=web_safari,web",
            "--user-agent", YT_DLP_USER_AGENT,
            video_info.url
        ]

        # Add live-specific flags only if it's a live stream
        if is_live:
            yt_dlp_cmd.append("--live-from-start")

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

    def convert_mkv_to_mp4(self, mkv_path: str) -> Optional[str]:
        """
        Convert MKV file to MP4 format using FFmpeg.

        Args:
            mkv_path: Path to the MKV file

        Returns:
            Path to the MP4 file or None if conversion fails
        """
        if not os.path.exists(mkv_path):
            logger.error(f"❌ MKV file not found: {mkv_path}")
            return None

        mp4_path = mkv_path.replace('.mkv', '.mp4')
        
        try:
            logger.info(f"🔄 Converting MKV to MP4: {os.path.basename(mkv_path)}")
            
            # FFmpeg command to convert MKV to MP4 (fast copy, no re-encoding)
            cmd = [
                'ffmpeg',
                '-i', mkv_path,
                '-c', 'copy',  # Copy codecs (no re-encoding)
                '-movflags', '+faststart',  # Optimize for streaming
                '-y',  # Overwrite output file if exists
                mp4_path
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=40000  # ~11 hours timeout
            )
            
            if result.returncode == 0 and os.path.exists(mp4_path):
                logger.info(f"✅ MP4 conversion successful: {os.path.basename(mp4_path)}")
                return mp4_path
            else:
                error_msg = result.stderr.decode('utf-8', errors='replace')
                logger.error(f"❌ FFmpeg conversion failed: {error_msg}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("❌ FFmpeg conversion timed out")
            return None
        except FileNotFoundError:
            logger.error("❌ FFmpeg not found. Please install FFmpeg.")
            return None
        except Exception as e:
            logger.error(f"❌ Error converting MKV to MP4: {e}", exc_info=True)
            return None

    def extract_audio_from_video(self, video_path: str) -> Optional[MediaFile]:
        """
        Extract audio from video file as MP3.

        Args:
            video_path: Path to the video file (MP4, MKV, etc.)

        Returns:
            MediaFile object with audio file or None if extraction fails
        """
        logger.info(f"🎵 extract_audio_from_video called")
        logger.info(f"   Input path: {video_path}")
        logger.info(f"   File exists: {os.path.exists(video_path)}")
        
        if not os.path.exists(video_path):
            logger.error(f"❌ Video file not found: {video_path}")
            return None

        # Generate MP3 filename (replace extension)
        base_path = os.path.splitext(video_path)[0]
        mp3_path = f"{base_path}.mp3"
        
        logger.info(f"   Output path: {mp3_path}")
        
        try:
            logger.info(f"🎵 Extracting audio from: {os.path.basename(video_path)}")
            
            # FFmpeg command to extract audio as MP3
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'libmp3lame',  # MP3 codec
                '-ab', YT_DLP_AUDIO_QUALITY,  # Audio bitrate
                '-ar', '44100',  # Sample rate
                '-y',  # Overwrite output file if exists
                mp3_path
            ]
            
            logger.info(f"   Running FFmpeg command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=40000  # ~11 hours timeout
            )
            
            logger.info(f"   FFmpeg return code: {result.returncode}")
            logger.info(f"   Output file exists: {os.path.exists(mp3_path)}")
            
            if result.returncode == 0 and os.path.exists(mp3_path):
                logger.info(f"✅ Audio extracted: {os.path.basename(mp3_path)}")
                return MediaFile(
                    path=mp3_path,
                    filename=os.path.basename(mp3_path),
                    file_type='audio'
                )
            else:
                error_msg = result.stderr.decode('utf-8', errors='replace')
                logger.error(f"❌ FFmpeg audio extraction failed")
                logger.error(f"   Return code: {result.returncode}")
                logger.error(f"   STDERR: {error_msg[-500:]}")  # Last 500 chars
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("❌ FFmpeg audio extraction timed out")
            return None
        except FileNotFoundError:
            logger.error("❌ FFmpeg not found. Please install FFmpeg.")
            logger.error("   Install with: sudo apt-get install ffmpeg")
            return None
        except Exception as e:
            logger.error(f"❌ Error extracting audio: {e}", exc_info=True)
            return None

    def compress_video(self, input_path: str) -> Optional[str]:
        """
        Compress video using FFmpeg with H.264 codec to save storage space.
        
        This method reduces video file size while maintaining acceptable quality
        using the CRF (Constant Rate Factor) encoding method. The compressed
        video is optimized for web playback with the faststart flag.
        
        Args:
            input_path: Path to the video file to compress
            
        Returns:
            str: Path to compressed video file, or None if compression fails
        """
        from config.settings import COMPRESSION_CRF, COMPRESSION_PRESET, COMPRESSION_AUDIO_BITRATE
        
        logger.info(f"🗜️ compress_video called")
        logger.info(f"   Input path: {input_path}")
        logger.info(f"   File exists: {os.path.exists(input_path)}")
        
        if not os.path.exists(input_path):
            logger.error(f"❌ Video file not found: {input_path}")
            return None
        
        # Get original file size
        original_size = os.path.getsize(input_path) / (1024 * 1024)  # MB
        logger.info(f"   Original file size: {original_size:.2f} MB")
        
        # Generate compressed filename (add _compressed suffix before extension)
        base_path, ext = os.path.splitext(input_path)
        compressed_path = f"{base_path}_compressed{ext}"
        
        logger.info(f"   Output path: {compressed_path}")
        logger.info(f"   Compression settings: CRF={COMPRESSION_CRF}, Preset={COMPRESSION_PRESET}")
        
        try:
            logger.info(f"🗜️ Compressing video: {os.path.basename(input_path)}")
            
            # FFmpeg command for video compression
            # - libx264: H.264 codec (widely compatible)
            # - CRF: Quality control (lower = better quality, larger file)
            # - preset: Speed vs compression efficiency
            # - r: Limit framerate to 30fps (sufficient for talks/presentations)
            # - aac: Audio codec for compatibility
            # - movflags +faststart: Optimize for web playback (moov atom at start)
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-c:v', 'libx264',              # Video codec
                '-crf', str(COMPRESSION_CRF),   # Quality (0-51, 23=default, 28=high compression)
                '-preset', COMPRESSION_PRESET,  # Encoding speed/efficiency
                '-r', '30',                     # Limit to 30 FPS
                '-c:a', 'aac',                  # Audio codec
                '-b:a', COMPRESSION_AUDIO_BITRATE,  # Audio bitrate
                '-movflags', '+faststart',      # Web optimization
                '-y',                           # Overwrite output file
                compressed_path
            ]
            
            logger.info(f"   Running FFmpeg command: {' '.join(cmd)}")
            
            # Run compression with timeout (allow more time for large files)
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=40000  # ~11 hours timeout (aligned with Celery limits)
            )
            
            logger.info(f"   FFmpeg return code: {result.returncode}")
            logger.info(f"   Output file exists: {os.path.exists(compressed_path)}")
            
            if result.returncode == 0 and os.path.exists(compressed_path):
                # Get compressed file size and calculate compression ratio
                compressed_size = os.path.getsize(compressed_path) / (1024 * 1024)  # MB
                compression_ratio = ((original_size - compressed_size) / original_size) * 100
                
                logger.info(f"✅ Video compressed successfully!")
                logger.info(f"   Original size: {original_size:.2f} MB")
                logger.info(f"   Compressed size: {compressed_size:.2f} MB")
                logger.info(f"   Space saved: {original_size - compressed_size:.2f} MB ({compression_ratio:.1f}%)")
                
                return compressed_path
            else:
                error_msg = result.stderr.decode('utf-8', errors='replace')
                logger.error(f"❌ FFmpeg compression failed")
                logger.error(f"   Return code: {result.returncode}")
                logger.error(f"   STDERR (last 500 chars): {error_msg[-500:]}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error("❌ FFmpeg compression timed out (exceeded 11 hours)")
            return None
        except FileNotFoundError:
            logger.error("❌ FFmpeg not found. Please install FFmpeg.")
            logger.error("   Install with: sudo apt-get install ffmpeg")
            return None
        except Exception as e:
            logger.error(f"❌ Error compressing video: {e}", exc_info=True)
            return None
