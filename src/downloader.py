"""Audio file downloader."""

import os
import re
import hashlib
import logging
import requests
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class Downloader:
    """Download podcast audio files."""

    def __init__(self, download_dir: str = "data/audio/downloaded",
                 processing_dir: str = "data/audio/processing",
                 archive_dir: str = "data/audio/archive",
                 max_file_size_mb: int = 500):
        """Initialize downloader.

        Args:
            download_dir: Directory for downloaded files
            processing_dir: Directory for files being processed
            archive_dir: Directory for archived files
            max_file_size_mb: Maximum file size to download (MB)
        """
        self.download_dir = Path(download_dir)
        self.processing_dir = Path(processing_dir)
        self.archive_dir = Path(archive_dir)
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        # Create directories if they don't exist
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.processing_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def download_audio(self, audio_url: str, filename: str) -> tuple[Optional[str], Optional[float]]:
        """Download audio file.

        Args:
            audio_url: URL to audio file
            filename: Filename to save as (in download_dir)

        Returns:
            Tuple of (file_path, file_size_mb) or (None, None) if failed
        """
        filepath = self.download_dir / filename

        try:
            logger.info(f"Downloading audio: {audio_url}")

            # Stream download to check size
            response = requests.get(audio_url, stream=True, timeout=30)
            response.raise_for_status()

            # Check file size from headers
            content_length = response.headers.get('content-length')
            file_size_bytes = None
            if content_length:
                file_size_bytes = int(content_length)
                if file_size_bytes > self.max_file_size_bytes:
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    actual_mb = file_size_bytes / (1024 * 1024)
                    logger.error(
                        f"File size {actual_mb:.1f}MB exceeds limit {max_mb:.1f}MB: {audio_url}"
                    )
                    return None, None

            # Download file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Get actual file size after download
            actual_size_bytes = filepath.stat().st_size
            file_size_mb = actual_size_bytes / (1024 * 1024)

            logger.info(f"Downloaded audio to: {filepath} ({file_size_mb:.2f} MB)")
            return str(filepath), file_size_mb

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download audio from {audio_url}: {e}")
            # Clean up partial download
            if filepath.exists():
                filepath.unlink()
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error downloading audio: {e}")
            if filepath.exists():
                filepath.unlink()
            return None, None

    def move_to_processing(self, filepath: str) -> str:
        """Move file from downloaded to processing directory.

        Args:
            filepath: Current file path

        Returns:
            New file path in processing directory
        """
        src = Path(filepath)
        dst = self.processing_dir / src.name

        shutil.move(str(src), str(dst))
        logger.info(f"Moved to processing: {dst}")
        return str(dst)

    def move_to_archive(self, filepath: str) -> str:
        """Move file from processing to archive directory.

        Args:
            filepath: Current file path

        Returns:
            New file path in archive directory
        """
        src = Path(filepath)
        dst = self.archive_dir / src.name

        # If source doesn't exist, check if it's already in another directory
        if not src.exists():
            # Check downloaded directory
            alt_src = self.download_dir / src.name
            if alt_src.exists():
                src = alt_src

        if src.exists():
            shutil.move(str(src), str(dst))
            logger.info(f"Moved to archive: {dst}")
            return str(dst)
        else:
            logger.warning(f"File not found for archiving: {src}")
            return str(dst)

    def delete_audio_file(self, filepath: str):
        """Delete audio file from any directory.

        Args:
            filepath: File path to delete
        """
        path = Path(filepath)

        # Try exact path first
        if path.exists():
            path.unlink()
            logger.info(f"Deleted audio file: {filepath}")
            return

        # Try searching in all directories
        filename = path.name
        for directory in [self.download_dir, self.processing_dir, self.archive_dir]:
            candidate = directory / filename
            if candidate.exists():
                candidate.unlink()
                logger.info(f"Deleted audio file: {candidate}")
                return

        logger.warning(f"Audio file not found for deletion: {filepath}")

    @staticmethod
    def sanitize_filename(title: str, published_date: Optional[str] = None,
                         episode_guid: Optional[str] = None,
                         max_length: int = 100) -> str:
        """Create sanitized filename from episode title and date.

        Args:
            title: Episode title
            published_date: ISO format date string
            episode_guid: Episode GUID (used for hash fallback if date missing)
            max_length: Maximum length for episode name part

        Returns:
            Sanitized filename in format: yyyymmdd-episode-name.mp3
        """
        # Extract date prefix
        date_prefix = ""
        if published_date:
            try:
                dt = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
                date_prefix = dt.strftime("%Y%m%d")
            except (ValueError, AttributeError):
                logger.error(f"Could not parse date: {published_date}")

        if not date_prefix:
            # Fallback to hash of GUID for deterministic naming
            if episode_guid:
                hash_prefix = hashlib.sha256(episode_guid.encode()).hexdigest()[:8]
                date_prefix = hash_prefix
            else:
                # Last resort: use today's date
                date_prefix = datetime.now().strftime("%Y%m%d")

        # Sanitize title
        # Remove special characters, keep alphanumeric and spaces
        clean_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title)
        # Replace spaces with hyphens
        clean_title = re.sub(r'\s+', '-', clean_title)
        # Remove multiple hyphens
        clean_title = re.sub(r'-+', '-', clean_title)
        # Convert to lowercase
        clean_title = clean_title.lower()
        # Strip leading/trailing hyphens
        clean_title = clean_title.strip('-')
        # Limit length
        clean_title = clean_title[:max_length]

        # Construct filename
        filename = f"{date_prefix}-{clean_title}.mp3"
        return filename
