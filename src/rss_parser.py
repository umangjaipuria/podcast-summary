"""RSS feed parser for podcast episodes."""

import feedparser
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from time import mktime

logger = logging.getLogger(__name__)


class RSSParser:
    """Parse podcast RSS feeds."""

    def __init__(self, max_audio_length_minutes: int = 240):
        """Initialize RSS parser.

        Args:
            max_audio_length_minutes: Skip episodes longer than this
        """
        self.max_audio_length_minutes = max_audio_length_minutes

    def fetch_episodes(self, rss_url: str, check_last_n: int = 3) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Fetch and parse episodes from RSS feed.

        Args:
            rss_url: RSS feed URL
            check_last_n: Number of recent episodes to return

        Returns:
            Tuple of (episodes list, podcast metadata dict)

        Raises:
            Exception: If there's an error fetching or parsing the feed
        """
        logger.info(f"Fetching RSS feed: {rss_url}")
        feed = feedparser.parse(rss_url)

        # Check for HTTP errors
        if hasattr(feed, 'status') and feed.status >= 400:
            raise Exception(f"HTTP error {feed.status} fetching RSS feed")

        if feed.bozo and feed.bozo_exception:
            # Only raise for serious parsing errors, not minor issues
            if isinstance(feed.bozo_exception, (IOError, OSError)):
                raise Exception(f"Network error fetching RSS feed: {feed.bozo_exception}")

        if not feed.entries:
            logger.warning(f"No entries found in RSS feed: {rss_url}")
            return [], {}

        # Extract podcast-level metadata
        podcast_metadata = self._extract_podcast_metadata(feed)

        episodes = []
        for entry in feed.entries[:check_last_n]:
            episode = self._parse_entry(entry, rss_url)
            if episode:
                # Check duration limit
                duration_minutes = episode.get('duration_minutes')
                if duration_minutes and duration_minutes > self.max_audio_length_minutes:
                    logger.warning(
                        f"Skipping episode '{episode['title']}': "
                        f"duration {duration_minutes} min exceeds limit {self.max_audio_length_minutes} min"
                    )
                    continue

                episodes.append(episode)

        logger.info(f"Parsed {len(episodes)} episodes from {rss_url}")
        return episodes, podcast_metadata

    def _extract_podcast_metadata(self, feed) -> Dict[str, Any]:
        """Extract podcast-level metadata from feed.

        Args:
            feed: feedparser feed object

        Returns:
            Dictionary with podcast title, description, author, link, image_url, categories
        """
        metadata = {}

        if not hasattr(feed, 'feed'):
            return metadata

        # Extract podcast title
        if hasattr(feed.feed, 'title') and feed.feed.title:
            metadata['title'] = feed.feed.title

        # Extract podcast description (prioritize podcast-standard fields)
        description = None
        if hasattr(feed.feed, 'itunes_summary') and feed.feed.itunes_summary:
            description = feed.feed.itunes_summary
        elif hasattr(feed.feed, 'description') and feed.feed.description:
            description = feed.feed.description
        elif hasattr(feed.feed, 'summary') and feed.feed.summary:
            description = feed.feed.summary
        elif hasattr(feed.feed, 'itunes_subtitle') and feed.feed.itunes_subtitle:
            description = feed.feed.itunes_subtitle

        if description:
            metadata['description'] = description

        # Extract podcast author (prioritize iTunes field for podcast feeds)
        author = None
        if hasattr(feed.feed, 'itunes_author') and feed.feed.itunes_author:
            author = feed.feed.itunes_author
        elif hasattr(feed.feed, 'author') and feed.feed.author:
            author = feed.feed.author
        elif hasattr(feed.feed, 'author_detail') and hasattr(feed.feed.author_detail, 'name') and feed.feed.author_detail.name:
            author = feed.feed.author_detail.name

        if author:
            metadata['author'] = author

        # Extract podcast link
        if hasattr(feed.feed, 'link') and feed.feed.link:
            metadata['link'] = feed.feed.link

        # Extract podcast image URL (for email fallback when episode image is missing)
        image_url = None
        if hasattr(feed.feed, 'itunes_image') and feed.feed.itunes_image:
            # iTunes image can be a dict with 'href' or a string
            if isinstance(feed.feed.itunes_image, dict):
                image_url = feed.feed.itunes_image.get('href')
            elif isinstance(feed.feed.itunes_image, str):
                image_url = feed.feed.itunes_image
        elif hasattr(feed.feed, 'image') and feed.feed.image:
            # Standard RSS image element (has url sub-element)
            if isinstance(feed.feed.image, dict):
                image_url = feed.feed.image.get('href') or feed.feed.image.get('url')
            elif isinstance(feed.feed.image, str):
                image_url = feed.feed.image

        if image_url:
            metadata['image_url'] = image_url

        # Extract podcast categories
        categories = []
        if hasattr(feed.feed, 'tags') and feed.feed.tags:
            # feedparser normalizes categories to 'tags' list
            for tag in feed.feed.tags:
                if isinstance(tag, dict):
                    # tag has 'term' (category name) and optional 'scheme' (category type)
                    term = tag.get('term')
                    if term and term not in categories:
                        categories.append(term)
                elif isinstance(tag, str) and tag not in categories:
                    categories.append(tag)

        if categories:
            metadata['categories'] = categories

        return metadata

    def _parse_entry(self, entry, rss_url: str) -> Optional[Dict[str, Any]]:
        """Parse individual feed entry.

        Args:
            entry: feedparser entry object
            rss_url: RSS feed URL (for logging)

        Returns:
            Episode dictionary or None if invalid
        """
        try:
            # Extract GUID (required for deduplication)
            guid = entry.get('id') or entry.get('guid')
            if not guid:
                logger.error(f"Entry missing GUID, skipping: {entry.get('title', 'Unknown')}")
                return None

            # Extract audio URL and file size from enclosures
            audio_url, file_size_bytes = self._extract_audio_url(entry)
            if not audio_url:
                logger.error(f"No audio URL found for episode: {entry.get('title', 'Unknown')}")
                return None

            # Convert file size to MB
            file_size_mb = None
            if file_size_bytes:
                file_size_mb = file_size_bytes / (1024 * 1024)

            # Extract image URL
            image_url = self._extract_image_url(entry)

            # Parse published date with fallbacks
            published_date = self._parse_published_date(entry)

            # Parse duration
            duration_minutes = self._parse_duration(entry)

            # Get raw RSS for this entry (convert to JSON-serializable format)
            import json
            # Convert feedparser entry to dict, removing non-serializable objects
            entry_dict = dict(entry)
            # Remove time.struct_time objects that aren't JSON serializable
            if 'published_parsed' in entry_dict:
                del entry_dict['published_parsed']
            if 'updated_parsed' in entry_dict:
                del entry_dict['updated_parsed']
            raw_rss = json.dumps(entry_dict, ensure_ascii=False)

            return {
                'guid': guid,
                'title': entry.get('title', ''),
                'description': entry.get('description', '') or entry.get('summary', ''),
                'link': entry.get('link', ''),
                'audio_url': audio_url,
                'image_url': image_url,
                'published_date': published_date,
                'duration_minutes': duration_minutes,
                'file_size_mb': file_size_mb,
                'raw_rss': raw_rss
            }

        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None

    def _extract_audio_url(self, entry) -> tuple[Optional[str], Optional[int]]:
        """Extract audio URL and file size from entry enclosures.

        Returns:
            Tuple of (audio_url, file_size_in_bytes)
        """
        # Check enclosures for audio files
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('audio/'):
                    url = enclosure.get('href') or enclosure.get('url')
                    # Try to extract file size (length attribute in RSS)
                    file_size = None
                    if 'length' in enclosure:
                        try:
                            file_size = int(enclosure['length'])
                        except (ValueError, TypeError):
                            logger.debug(f"Could not parse file size: {enclosure.get('length')}")
                    return url, file_size

        # Fallback to links (no file size available)
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio/'):
                    return link.get('href'), None

        return None, None

    def _extract_image_url(self, entry) -> Optional[str]:
        """Extract episode image/artwork URL."""
        # Try iTunes image first
        if hasattr(entry, 'image'):
            if isinstance(entry.image, dict):
                return entry.image.get('href')
            elif isinstance(entry.image, str):
                return entry.image

        # Try media:thumbnail
        if hasattr(entry, 'media_thumbnail'):
            if entry.media_thumbnail and len(entry.media_thumbnail) > 0:
                return entry.media_thumbnail[0].get('url')

        # Try media:content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image/'):
                    return media.get('url')

        # Try links
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('image/'):
                    return link.get('href')

        return None

    def _parse_published_date(self, entry) -> Optional[str]:
        """Parse published date with multiple fallbacks.

        Args:
            entry: feedparser entry object

        Returns:
            ISO format date string or None if unparseable
        """
        # Try published_parsed first
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                return datetime.fromtimestamp(mktime(entry.published_parsed)).isoformat()
            except (ValueError, TypeError, OverflowError) as e:
                logger.debug(f"Could not parse published_parsed: {e}")

        # Try updated_parsed
        if hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            try:
                return datetime.fromtimestamp(mktime(entry.updated_parsed)).isoformat()
            except (ValueError, TypeError, OverflowError) as e:
                logger.debug(f"Could not parse updated_parsed: {e}")

        # Try parsing published string as ISO format
        if hasattr(entry, 'published') and entry.published:
            try:
                # Try common ISO formats
                for fmt in ['%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(entry.published, fmt)
                        return dt.isoformat()
                    except ValueError:
                        continue
            except:
                logger.debug(f"Could not parse published string: {entry.published}")

        # Try parsing updated string as ISO format
        if hasattr(entry, 'updated') and entry.updated:
            try:
                for fmt in ['%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(entry.updated, fmt)
                        return dt.isoformat()
                    except ValueError:
                        continue
            except:
                logger.debug(f"Could not parse updated string: {entry.updated}")

        # No date found
        return None

    def _parse_duration(self, entry) -> Optional[int]:
        """Parse duration from entry and convert to minutes.

        Supports:
        - HH:MM:SS format
        - MM:SS format
        - Seconds as integer

        Returns:
            Duration in minutes or None if not found/parseable
        """
        # Try itunes:duration
        duration = None
        if hasattr(entry, 'itunes_duration'):
            duration = entry.itunes_duration

        if not duration:
            return None

        try:
            # If it's already an integer (seconds)
            if isinstance(duration, int):
                return duration // 60

            # If it's a string, parse it
            duration = str(duration).strip()

            # Check for HH:MM:SS or MM:SS format
            if ':' in duration:
                parts = duration.split(':')
                if len(parts) == 3:  # HH:MM:SS
                    hours, minutes, seconds = map(int, parts)
                    return hours * 60 + minutes + (1 if seconds > 0 else 0)
                elif len(parts) == 2:  # MM:SS
                    minutes, seconds = map(int, parts)
                    return minutes + (1 if seconds > 0 else 0)

            # Try parsing as integer seconds
            seconds = int(duration)
            return seconds // 60

        except (ValueError, AttributeError) as e:
            logger.debug(f"Could not parse duration '{duration}': {e}")
            return None
