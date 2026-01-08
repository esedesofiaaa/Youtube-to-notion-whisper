#!/usr/bin/env python3
"""
YouTube Downloader - A simple command-line tool for downloading YouTube videos
"""

import os
import sys
import click
import yt_dlp
import whisper
import subprocess
import re
import shutil
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.text import Text

# Load environment variables
load_dotenv()

# Initialize Rich console
console = Console()

class TranscriptProcessor:
    """Process transcripts and generate comprehensive summaries"""
    
    def __init__(self):
        self.download_dir = Path(os.getenv('DOWNLOAD_DIR', './downloads'))
    
    def extract_text_from_srt(self, srt_file):
        """Extract clean text from SRT subtitle file"""
        try:
            with open(srt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Remove timestamps and subtitle numbers, keep only text
            lines = content.split('\n')
            text_lines = []
            
            for line in lines:
                line = line.strip()
                # Skip empty lines, timestamps, and subtitle numbers
                if (line and 
                    not re.match(r'^\d+$', line) and  # Skip subtitle numbers
                    not re.match(r'^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$', line) and  # Skip timestamps
                    not line.startswith('-->')):
                    text_lines.append(line)
            
            return ' '.join(text_lines)
        except Exception as e:
            console.print(f"❌ Error reading SRT file {srt_file}: {str(e)}", style="red")
            return ""
    
    def save_clean_transcript(self, srt_file, title, output_dir=None):
        """Save clean transcript without timestamps"""
        try:
            with open(srt_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # Remove timestamps and subtitle numbers, keep only text
            lines = content.split('\n')
            clean_lines = []

            for line in lines:
                line = line.strip()
                # Skip empty lines, timestamps, and subtitle numbers
                if (line and
                    not re.match(r'^\d+$', line) and  # Skip subtitle numbers
                    not re.match(r'^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$', line) and  # Skip timestamps
                    not line.startswith('-->')):
                    clean_lines.append(line)

            # Save as clean text file
            if output_dir:
                output_file = output_dir / f"{title}_transcript.txt"
            else:
                output_file = self.download_dir / f"{title}_transcript.txt"
                
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# {title}\n\n")
                f.write("Full Transcript (Clean Text)\n")
                f.write("=" * 50 + "\n\n")
                f.write('\n'.join(clean_lines))

            console.print(f"📄 Clean transcript saved: {output_file.name}")
            return str(output_file)
            
        except Exception as e:
            console.print(f"❌ Error saving clean transcript: {str(e)}", style="red")
            return None
    
    def generate_summary(self, text, title):
        """Generate a comprehensive summary using OpenAI or fallback method"""
        try:
            # Try to use OpenAI if API key is available
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if openai_api_key:
                return self.generate_openai_summary(text, title, openai_api_key)
            else:
                return self.generate_fallback_summary(text, title)
        except Exception as e:
            console.print(f"⚠️  Error generating summary: {str(e)}")
            return self.generate_fallback_summary(text, title)
    
    def generate_openai_summary(self, text, title, api_key):
        """Generate summary using OpenAI API"""
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            
            prompt = f"""
            Please analyze the following transcript from a YouTube video titled "{title}" and provide:
            
            1. **TLDR (Too Long; Didn't Read)** - A 2-3 sentence summary of the main points
            2. **Key Topics** - List the main topics discussed
            3. **Important Points** - Highlight the most important insights or takeaways
            4. **Action Items** - Any actionable advice or next steps mentioned
            5. **Summary** - A comprehensive 3-4 paragraph summary
            
            Transcript:
            {text[:4000]}  # Limit to first 4000 chars to stay within token limits
            
            Format the response in clean markdown.
            """
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            console.print(f"⚠️  OpenAI API error: {str(e)}")
            return self.generate_fallback_summary(text, title)
    
    def generate_fallback_summary(self, text, title):
        """Generate summary using basic text analysis"""
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        # Simple keyword extraction
        words = re.findall(r'\b\w+\b', text.lower())
        word_freq = {}
        for word in words:
            if len(word) > 3:  # Skip short words
                word_freq[word] = word_freq.get(word, 0) + 1
        
        # Get top keywords
        top_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Create summary
        summary = f"""# {title}

## TLDR
This video covers {len(sentences)} main points about {', '.join([kw[0] for kw in top_keywords[:5]])}.

## Key Topics
- {chr(10).join([f"- {kw[0]} (mentioned {kw[1]} times)" for kw in top_keywords[:8]])}

## Important Points
- Video contains approximately {len(sentences)} key statements
- Main focus areas: {', '.join([kw[0] for kw in top_keywords[:3]])}
- Duration and content suggest comprehensive coverage of the topic

## Summary
This video provides detailed coverage of {title.lower()}. The transcript contains {len(sentences)} main points covering various aspects of the subject matter. Key themes include {', '.join([kw[0] for kw in top_keywords[:5]])}.

The content appears to be educational or informational in nature, with multiple discussion points and detailed explanations throughout the presentation.

For the most accurate and detailed information, please refer to the full transcript or watch the original video.
"""
        return summary

class YouTubeDownloader:
    def __init__(self):
        self.download_dir = Path(os.getenv('DOWNLOAD_DIR', './downloads'))
        self.default_quality = os.getenv('DEFAULT_QUALITY', 'best')
        self.default_audio_format = os.getenv('DEFAULT_AUDIO_FORMAT', 'mp3')
        self.max_concurrent = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', '3'))
        self.show_progress = os.getenv('SHOW_PROGRESS', 'true').lower() == 'true'
        self.verbose = os.getenv('VERBOSE', 'false').lower() == 'true'
        
        # Ensure download directory exists
        self.download_dir.mkdir(exist_ok=True)

    def get_video_title(self, url):
        """Get the actual video title from YouTube without downloading"""
        try:
            opts = {
                'quiet': True,
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                },
                'extractor_args': {
                    'youtube': {
                        'player_skip': ['webpage'],
                    }
                },
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('title', None)
        except Exception as e:
            console.print(f"⚠️  Warning: Could not get video title: {str(e)}")
            return None

    def progress_hook(self, d):
        """Progress hook for yt-dlp"""
        if d['status'] == 'downloading':
            if self.show_progress:
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percentage = (downloaded / total) * 100
                    speed = d.get('speed', 0)
                    if speed:
                        speed_mb = speed / 1024 / 1024
                        console.print(f"Downloading: {percentage:.1f}% - {speed_mb:.1f} MB/s")
        elif d['status'] == 'finished':
            console.print(f"✓ Downloaded: {d['filename']}")

    def get_ydl_opts(self, audio_only=False, quality=None, output_template=None):
        """Get yt-dlp options"""
        if quality is None:
            quality = self.default_quality
        
        if output_template is None:
            output_template = str(self.download_dir / '%(title)s.%(ext)s')
        
        opts = {
            'outtmpl': output_template,
            'progress_hooks': [self.progress_hook] if self.show_progress else [],
            'verbose': self.verbose,
            'nopart': True,  # Don't create .part files
            'no_continue': True,  # Don't resume downloads (overwrites existing)
            'overwrites': True,  # Overwrite existing files
            'merge_output_format': 'mp4',  # Ensure merged output is MP4
            'writesubtitles': True,  # Download manual subtitles
            'writeautomaticsub': True,  # Download auto-generated subtitles
            'subtitleslangs': ['en'],  # Download English subtitles
            'subtitlesformat': 'srt',  # Save as SRT format
            # Add headers and options to bypass 403 errors
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            # Additional options to avoid bot detection
            # Let yt-dlp automatically choose the best client for format availability
            # The updated yt-dlp version should handle client selection better
            'extractor_args': {
                'youtube': {
                    'player_skip': ['webpage'],
                }
            },
            # Prefer higher quality formats - sort by resolution descending
            'format_sort': ['+res', '+ext:mp4:m4a', '+codec:h264', '+fps'],
            'prefer_free_formats': False,
        }
        
        # Add postprocessors for merging video and audio if not audio-only
        if not audio_only:
            # yt-dlp automatically merges video+audio when using + format
            opts['postprocessors'] = []
            
            # For QuickTime compatibility: prefer H.264 in format selection (already done above)
            # If we still get VP9, we'll need to convert it. For now, just remux to MP4.
            # Note: VP9 videos won't work in QuickTime, but H.264 videos will.
            # The format_sort above already prefers H.264 codecs, so we should get H.264 when available.
            opts['postprocessors'].append({
                'key': 'FFmpegVideoRemuxer',
                'preferedformat': 'mp4',
            })
            
            # Add subtitle post-processor to create main .srt file
            if 'writesubtitles' in opts or 'writeautomaticsub' in opts:
                opts['postprocessors'].append({
                    'key': 'FFmpegSubtitlesConvertor',
                    'format': 'srt'
                })
            

        
        if audio_only:
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': self.default_audio_format,
                }],
            })
        else:
            # Use format that includes both video and audio
            if quality == 'best':
                # Get the best quality available by merging best video + best audio
                # Explicitly avoid low quality formats - minimum 480p
                # Fallback chain: merge 1080p+ > merge 720p+ > merge 480p+ > merge best (but not format 18)
                opts['format'] = 'bestvideo[height>=1080]+bestaudio/bestvideo[height>=720]+bestaudio/bestvideo[height>=480]+bestaudio/bestvideo+bestaudio'
            elif quality == '720p':
                # Download best video + best audio up to 720p, with fallbacks
                opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/bestvideo+bestaudio/best'
            elif quality == '1080p':
                # Download best video + best audio up to 1080p, with fallbacks
                opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/bestvideo+bestaudio/best'
            else:
                opts['format'] = quality
        
        return opts

    def download_video(self, url, audio_only=False, quality=None, generate_transcript=False):
        """Download a single video"""
        try:
            console.print(f"🎬 Starting download: {url}")
            
            opts = self.get_ydl_opts(audio_only, quality)
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                # Get video info first
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown Title')
                
                console.print(f"📹 Title: {title}")
                console.print(f"📁 Saving to: {self.download_dir}")
                
                # Download the video
                ydl.download([url])
                
                # Find the downloaded video file (merged MP4)
                # yt-dlp may sanitize the filename, so we need to be more flexible
                video_files = list(self.download_dir.glob("*.mp4"))
                # Find the most recently downloaded MP4 file that matches the title pattern
                matching_files = []
                for file in video_files:
                    # Check if the filename contains key parts of the title
                    title_parts = [part.lower() for part in title.lower().split() if len(part) > 2]
                    filename_lower = file.name.lower()
                    if any(part in filename_lower for part in title_parts):
                        matching_files.append(file)
                
                if matching_files:
                    # Use the most recently modified file
                    video_path = max(matching_files, key=lambda x: x.stat().st_mtime)
                    console.print(f"📹 Found downloaded video: {video_path.name}")
                    
                    # Check if video needs conversion for QuickTime compatibility
                    self.convert_for_quicktime_if_needed(video_path)
                    
                    # Clean up intermediate files
                    self.cleanup_intermediate_files(title)
                    
                    # Check if subtitles were downloaded
                    if not self.check_for_subtitles(video_path) and generate_transcript:
                        console.print("📝 No subtitles found, generating transcript with Whisper...")
                        # Create a temporary folder for transcript generation
                        temp_folder = self.download_dir / "temp_transcript"
                        temp_folder.mkdir(exist_ok=True)
                        self.generate_transcript(str(video_path), temp_folder)
                        # Move transcript back to downloads root
                        for transcript_file in temp_folder.glob("*.srt"):
                            transcript_file.rename(self.download_dir / transcript_file.name)
                        # Also move the clean transcript file if it exists
                        for transcript_file in temp_folder.glob("*_transcript.txt"):
                            transcript_file.rename(self.download_dir / transcript_file.name)
                        # Remove the temp directory and all its contents
                        shutil.rmtree(temp_folder)
                
                console.print(f"✅ Download completed: {title}")
                return True
                
        except Exception as e:
            console.print(f"❌ Error downloading {url}: {str(e)}", style="red")
            return False

    def generate_transcript(self, video_path, output_dir=None):
        """Generate transcript using Whisper if no subtitles are available"""
        try:
            video_name = Path(video_path).stem
            if output_dir:
                output_path = output_dir / f"{video_name}.srt"
            else:
                output_path = str(Path(video_path).with_suffix('.srt'))
            
            console.print(f"🎤 Generating transcript for: {Path(video_path).name}")
            
            # Load Whisper model
            model = whisper.load_model("base")
            
            # Transcribe the video
            result = model.transcribe(video_path)
            
            # Save as SRT format
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(result['segments'], 1):
                    start_time = self.format_time(segment['start'])
                    end_time = self.format_time(segment['end'])
                    text = segment['text'].strip()
                    
                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{text}\n\n")
            
            console.print(f"✅ Transcript saved: {output_path}")
            
            # If we have an output directory, also save clean transcript
            if output_dir:
                processor = TranscriptProcessor()
                processor.save_clean_transcript(str(output_path), video_name, output_dir)
            
            return True
            
        except Exception as e:
            console.print(f"❌ Error generating transcript: {str(e)}", style="red")
            return False
    
    def format_time(self, seconds):
        """Convert seconds to SRT time format (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def check_for_subtitles(self, video_path):
        """Check if subtitle files exist for the video"""
        video_name = Path(video_path).stem
        subtitle_path = Path(video_path).parent / f"{video_name}.en.srt"
        return subtitle_path.exists()
    
    def convert_for_quicktime_if_needed(self, video_path):
        """Convert VP9/VP8 videos to H.264 for QuickTime Player compatibility"""
        try:
            # Check video codec using ffprobe
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(video_path)],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                return  # ffprobe failed, skip conversion
            
            codec = result.stdout.strip().lower()
            
            # Only convert if codec is VP9 or VP8 (not H.264)
            if codec in ['vp9', 'vp8']:
                console.print(f"🔄 Converting {codec.upper()} to H.264 for QuickTime compatibility...")
                console.print("   This may take a while but preserves quality...")
                
                # Create temporary output file
                temp_path = video_path.parent / f"{video_path.stem}_temp.mp4"
                
                # Convert using FFmpeg with high quality settings
                convert_cmd = [
                    'ffmpeg', '-i', str(video_path),
                    '-c:v', 'libx264',
                    '-preset', 'slow',  # Better quality, slower encoding
                    '-crf', '18',  # High quality (visually lossless)
                    '-c:a', 'copy',  # Copy audio without re-encoding
                    '-y',  # Overwrite output file
                    str(temp_path)
                ]
                
                result = subprocess.run(convert_cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    # Replace original with converted file
                    video_path.unlink()
                    temp_path.rename(video_path)
                    console.print(f"✅ Converted to H.264 - QuickTime compatible!")
                else:
                    # Conversion failed, keep original
                    if temp_path.exists():
                        temp_path.unlink()
                    console.print(f"⚠️  Conversion failed, keeping original {codec.upper()} file")
                    console.print(f"   You can use VLC to play it, or convert manually with FFmpeg")
            else:
                # Already H.264 or other compatible codec
                if codec == 'h264':
                    console.print(f"✅ Video is already H.264 - QuickTime compatible!")
                    
        except subprocess.TimeoutExpired:
            console.print(f"⚠️  Codec check timed out, skipping conversion")
        except FileNotFoundError:
            console.print(f"⚠️  FFmpeg not found, skipping QuickTime conversion check")
        except Exception as e:
            console.print(f"⚠️  Could not check/convert video codec: {str(e)}")
    
    def cleanup_intermediate_files(self, title):
        """Clean up intermediate video files after merging"""
        try:
            # Remove intermediate video files (like .f609.mp4)
            intermediate_files = list(self.download_dir.glob(f"{title}.f*.mp4"))
            for file in intermediate_files:
                file.unlink()
                console.print(f"🗑️  Cleaned up: {file.name}")
        except Exception as e:
            console.print(f"⚠️  Warning: Could not clean up intermediate files: {str(e)}")
    
    def generate_comprehensive_summary(self):
        """Generate comprehensive summary documents for each downloaded video"""
        try:
            console.print("📝 Generating comprehensive summary documents...")
            
            # Find all video folders
            video_folders = [d for d in self.download_dir.iterdir() if d.is_dir()]
            if not video_folders:
                console.print("❌ No video folders found for summary generation", style="red")
                return
            
            processor = TranscriptProcessor()
            processed_count = 0
            
            # Process each video folder individually
            for video_folder in video_folders:
                title = video_folder.name
                console.print(f"📖 Processing video folder: {title}")
                
                # Look for SRT files in the video folder
                srt_files = list(video_folder.glob("*.srt"))
                if not srt_files:
                    console.print(f"⚠️  No transcript files found in {title}")
                    continue
                
                # Process the first SRT file found
                srt_file = srt_files[0]
                
                # Extract text from SRT
                text = processor.extract_text_from_srt(str(srt_file))
                if not text:
                    console.print(f"⚠️  No text extracted from {srt_file.name}")
                    continue
                
                # Generate summary
                summary = processor.generate_summary(text, title)
                
                # Create individual comprehensive document for this video
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                comprehensive_doc = f"""# {title} - Comprehensive Summary

*Generated on: {timestamp}*

---

{summary}

---

## Video Information
- **Title**: {title}
- **Video File**: {title}.mp4
- **Transcript File**: {srt_file.name}
- **Clean Transcript**: {title}_transcript.txt
- **Summary Generated**: {timestamp}
"""
                
                # Save individual comprehensive summary in the video folder
                output_file = video_folder / f"{title}_comprehensive_summary.md"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(comprehensive_doc)
                
                console.print(f"✅ Individual comprehensive summary saved: {output_file.name}")
                processed_count += 1
            
            if processed_count == 0:
                console.print("❌ No summaries generated", style="red")
                return
            
            console.print(f"📊 Generated {processed_count} individual comprehensive summaries")
            
        except Exception as e:
            console.print(f"❌ Error generating comprehensive summaries: {str(e)}", style="red")
    
    def download_batch(self, urls_file, generate_summaries=False):
        """Download multiple videos from a file"""
        try:
            with open(urls_file, 'r') as f:
                urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            console.print(f"📋 Found {len(urls)} URLs to download")
            
            success_count = 0
            for i, url in enumerate(urls, 1):
                console.print(f"\n[{i}/{len(urls)}] Processing: {url}")
                if self.download_video(url, generate_transcript=True):
                    success_count += 1
            
            # Generate comprehensive summary if requested
            if generate_summaries and success_count > 0:
                console.print(f"\n📝 Generating comprehensive summary for {success_count} downloaded videos...")
                self.generate_comprehensive_summary()
            
            console.print(f"\n🎉 Batch download completed: {success_count}/{len(urls)} successful")
            
        except FileNotFoundError:
            console.print(f"❌ File not found: {urls_file}", style="red")
        except Exception as e:
            console.print(f"❌ Error reading batch file: {str(e)}", style="red")

@click.command()
@click.argument('url', required=False)
@click.option('--audio-only', is_flag=True, help='Download audio only')
@click.option('--quality', help='Video quality (e.g., 720p, 480p, best, worst)')
@click.option('--batch', help='Download from a file containing URLs (one per line)')
@click.option('--list-formats', is_flag=True, help='List available formats for the video')
@click.option('--transcript', is_flag=True, help='Generate transcript if no subtitles available')
@click.option('--generate-summary', is_flag=True, help='Generate comprehensive summary of all downloaded videos')
def main(url, audio_only, quality, batch, list_formats, transcript, generate_summary):
    """YouTube Downloader - Download videos from YouTube"""
    
    # Show banner
    banner = Text("YouTube Downloader", style="bold blue")
    console.print(Panel(banner, style="blue"))
    
    downloader = YouTubeDownloader()
    
    if batch:
        downloader.download_batch(batch, generate_summaries=generate_summary)
    elif generate_summary:
        downloader.generate_comprehensive_summary()
    elif url:
        if list_formats:
            try:
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get('formats', [])
                    
                    console.print("\n📋 Available formats:")
                    console.print("Format ID | Extension | Resolution | Filesize | Note")
                    console.print("-" * 60)
                    
                    for f in formats:
                        format_id = f.get('format_id', 'N/A')
                        ext = f.get('ext', 'N/A')
                        resolution = f.get('resolution', 'N/A')
                        filesize = f.get('filesize', 'N/A')
                        if filesize != 'N/A':
                            filesize = f"{filesize / 1024 / 1024:.1f} MB"
                        note = f.get('format_note', '')
                        
                        console.print(f"{format_id:9} | {ext:9} | {resolution:10} | {filesize:8} | {note}")
                        
            except Exception as e:
                console.print(f"❌ Error listing formats: {str(e)}", style="red")
        else:
            downloader.download_video(url, audio_only, quality, transcript)
    else:
        console.print("❌ Please provide a URL or use --batch option", style="red")
        console.print("\nUsage examples:")
        console.print("  python youtube_downloader.py 'https://youtube.com/watch?v=VIDEO_ID'")
        console.print("  python youtube_downloader.py 'https://youtube.com/watch?v=VIDEO_ID' --audio-only")
        console.print("  python youtube_downloader.py 'https://youtube.com/watch?v=VIDEO_ID' --quality 720p")
        console.print("  python youtube_downloader.py --batch urls.txt")
        console.print("  python youtube_downloader.py 'https://youtube.com/watch?v=VIDEO_ID' --list-formats")

if __name__ == "__main__":
    main() 