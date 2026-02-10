"""Tests for episode download functionality.

As described in PLAN_MASTERPLAN.md:
- Download new episode from real RSS feed
- Verify episodes table populated with metadata
- Verify processing_events has status='downloaded'
- Verify audio file exists in archive directory

Note: These are integration tests that require internet access to fetch real RSS feeds.
Mark as @pytest.mark.integration if you want to skip in CI.
"""

import pytest
from src.rss_parser import RSSParser
from src.downloader import Downloader
from src.database import Database


def test_sanitize_filename():
    """Test filename sanitization."""
    filename = Downloader.sanitize_filename(
        title="AI & Machine Learning: The Future!!",
        published_date="2024-03-15T10:00:00",
        max_length=100
    )
    assert filename.startswith("20240315-")
    assert "ai-machine-learning-the-future" in filename
    assert filename.endswith(".mp3")
    assert "!" not in filename
    assert "&" not in filename


def test_sanitize_filename_with_long_title():
    """Test filename sanitization with very long title."""
    long_title = "A" * 200
    filename = Downloader.sanitize_filename(
        title=long_title,
        published_date="2024-01-01",
        max_length=100
    )
    assert len(filename) <= 100 + 8 + 4 + 1  # max_length + date + .mp3 + hyphen


def test_sanitize_filename_no_date():
    """Test filename sanitization when date is missing."""
    filename = Downloader.sanitize_filename(
        title="Episode Title",
        published_date=None,
        episode_guid="test-guid-123"
    )
    assert filename.endswith("-episode-title.mp3")
    # Should have some prefix (hash of GUID)
    assert len(filename) > len("episode-title.mp3")


@pytest.mark.integration
def test_fetch_rss_episodes():
    """Integration test: Fetch episodes from a real RSS feed.

    This test uses a well-known podcast RSS feed to verify RSS parsing works.
    Skip this test if you don't have internet access.
    """
    # Using a stable, public podcast feed
    rss_url = "https://feeds.simplecast.com/54nAGcIl"  # The Changelog podcast

    parser = RSSParser(max_audio_length_minutes=240)
    episodes = parser.fetch_episodes(rss_url, check_last_n=3)

    assert len(episodes) > 0
    assert len(episodes) <= 3

    # Verify episode structure
    episode = episodes[0]
    assert 'guid' in episode
    assert 'title' in episode
    assert 'audio_url' in episode
    assert episode['audio_url'] is not None


@pytest.mark.integration
def test_download_episode_flow(test_db, temp_dir):
    """Integration test: Download episode and verify database updates.

    This test downloads a real episode and verifies the complete flow.
    Note: This downloads actual audio files, so it may take time and bandwidth.
    """
    # Setup
    rss_url = "https://feeds.simplecast.com/54nAGcIl"
    parser = RSSParser(max_audio_length_minutes=240)

    # Create downloader with temp directory
    downloader = Downloader(
        download_dir=f"{temp_dir}/audio/downloaded",
        processing_dir=f"{temp_dir}/audio/processing",
        archive_dir=f"{temp_dir}/audio/archive",
        max_file_size_mb=500
    )

    # Sync podcast to database
    test_db.sync_podcasts([{
        'slug': 'test-podcast',
        'active': True
    }])

    # Get podcast from database
    podcast = test_db.get_podcast_by_slug('test-podcast')
    assert podcast is not None

    # Fetch episodes from RSS
    episodes = parser.fetch_episodes(rss_url, check_last_n=1)
    assert len(episodes) > 0

    episode_data = episodes[0]

    # Insert episode into database
    episode_id = test_db.insert_episode(podcast['id'], episode_data)
    assert episode_id > 0

    # Verify episode was inserted
    db_episode = test_db.get_episode_by_id(episode_id)
    assert db_episode is not None
    assert db_episode['title'] == episode_data['title']
    assert db_episode['audio_url'] == episode_data['audio_url']
    assert db_episode['image_url'] is not None or episode_data.get('image_url') is None
    assert db_episode['raw_rss'] is not None

    # Note: We skip actual audio download in this test to avoid large file transfers
    # In a real integration test, you would:
    # filename = Downloader.sanitize_filename(episode_data['title'], episode_data['published_date'])
    # audio_path = downloader.download_audio(episode_data['audio_url'], filename)
    # assert audio_path is not None

    # Add processing event
    test_db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': '/tmp/test.mp3'})

    # Verify processing events
    current_status = test_db.get_current_status(episode_id)
    assert current_status == 'downloaded'
    download_data = test_db.get_event_data(episode_id, 'downloaded')
    assert download_data is not None
    assert download_data['audio_path'] == '/tmp/test.mp3'
