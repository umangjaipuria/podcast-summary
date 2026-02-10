"""Pytest configuration and shared fixtures."""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
from src.database import Database
from src.config_loader import ConfigLoader


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def test_db(temp_dir):
    """Create a test database."""
    db_path = os.path.join(temp_dir, "test_podcasts.db")
    db = Database(db_path)
    db.connect()
    db.initialize_schema()
    yield db
    db.close()


@pytest.fixture
def test_config_files(temp_dir):
    """Create test configuration files."""
    # Create test podcasts.yaml
    podcasts_yaml = os.path.join(temp_dir, "test_podcasts.yaml")
    podcasts_content = """podcasts:
  - name: "Test Podcast"
    slug: "test-podcast"
    rss_url: "https://feeds.example.com/test"
    active: true
    emails:
      - "test@example.com"
    insights_prompt: "Test prompt for summaries"
"""

    with open(podcasts_yaml, 'w') as f:
        f.write(podcasts_content)

    # Create test config.yaml
    config_yaml = os.path.join(temp_dir, "test_config.yaml")
    config_content = """settings:
  check_last_n_episodes: 3
  max_audio_length_minutes: 240
  archive_retention_days: 15
  max_audio_file_size_mb: 500
  max_transcript_retention_days: 365
  system_email: "admin@example.com"

summary_system_prompt: |
  You are a podcast summarizer.

summary_default_prompt: |
  Provide a concise summary of this podcast episode.
"""

    with open(config_yaml, 'w') as f:
        f.write(config_content)

    # Create test .env
    env_file = os.path.join(temp_dir, "test.env")
    env_content = """ASSEMBLYAI_API_KEY=test-assemblyai-key
OPENAI_API_KEY=test-openai-key
RESEND_API_KEY=test-resend-key
"""

    with open(env_file, 'w') as f:
        f.write(env_content)

    return {
        'podcasts_yaml': podcasts_yaml,
        'config_yaml': config_yaml,
        'env_file': env_file
    }


@pytest.fixture
def test_config_loader(test_config_files):
    """Create a test configuration loader."""
    loader = ConfigLoader(
        podcasts_yaml=test_config_files['podcasts_yaml'],
        config_yaml=test_config_files['config_yaml'],
        env_file=test_config_files['env_file']
    )
    return loader


@pytest.fixture
def sample_episode_data():
    """Sample episode data for testing."""
    return {
        'guid': 'test-episode-guid-123',
        'title': 'Test Episode Title',
        'description': 'Test episode description',
        'link': 'https://example.com/episode',
        'audio_url': 'https://example.com/audio.mp3',
        'image_url': 'https://example.com/image.jpg',
        'published_date': '2024-01-15 10:00:00',
        'raw_rss': '<item>...</item>'
    }


@pytest.fixture
def sample_transcript():
    """Sample transcript text for testing."""
    return """Speaker 0: Welcome to the podcast!
Speaker 1: Thanks for having me.
Speaker 0: Let's talk about artificial intelligence.
Speaker 1: AI is transforming many industries."""
