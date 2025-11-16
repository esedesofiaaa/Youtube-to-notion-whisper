"""
YouTube downloader module using yt-dlp.
"""
import os
import datetime
import yt_dlp
from typing import Optional, Tuple
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
        Get video title and upload date using yt-dlp.

        Args:
            video_url: YouTube video URL

        Returns:
            VideoInfo object or None if fails
        """
        ydl_opts = self._build_yt_opts(quiet=True)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                title = info.get("title", "Unknown Title")

                # Parse upload date
                upload_date_str = info.get("upload_date")
                if upload_date_str:
                    upload_date = datetime.datetime.strptime(upload_date_str, "%Y%m%d").strftime(DATE_FORMAT)
                else:
                    ts = info.get("release_timestamp") or info.get("timestamp")
                    if ts:
                        upload_date = datetime.datetime.utcfromtimestamp(int(ts)).strftime(DATE_FORMAT)
                    else:
                        upload_date = datetime.datetime.now().strftime(DATE_FORMAT)
                        logger.warning(f"No upload date found for {video_url}, using current date")

                logger.info(f"📹 Video info: '{title}' ({upload_date})")
                return VideoInfo.from_url(video_url, title, upload_date)
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
