"""Tests for configuration validation.

As described in PLAN_MASTERPLAN.md, these tests verify:
1. Missing required field in podcasts.yaml → exit code 1
2. Invalid email format → exit code 1
3. Missing API key → exit code 1
4. Valid config → passes validation
"""

import os
import pytest
from src.config_loader import ConfigLoader, ConfigError


def test_valid_config(test_config_loader):
    """Test that valid configuration passes all validation checks."""
    result = test_config_loader.load_all()
    assert result is True
    assert len(test_config_loader.get_podcasts()) > 0
    assert test_config_loader.get_default_prompt() != ""


def test_missing_required_field_in_podcasts(temp_dir):
    """Test that missing required field in podcasts.yaml raises ConfigError."""
    # Create invalid podcasts.yaml (missing 'slug')
    podcasts_yaml = os.path.join(temp_dir, "invalid_podcasts.yaml")
    with open(podcasts_yaml, 'w') as f:
        f.write("""podcasts:
  - name: "Test Podcast"
    rss_url: "https://example.com/feed"
    active: true
""")

    config_yaml = os.path.join(temp_dir, "config.yaml")
    with open(config_yaml, 'w') as f:
        f.write("""settings:
  check_last_n_episodes: 3
  system_email: "admin@example.com"
summary_system_prompt: "System prompt"
summary_default_prompt: "Test prompt"
""")

    env_file = os.path.join(temp_dir, "test.env")
    with open(env_file, 'w') as f:
        f.write("""ASSEMBLYAI_API_KEY=test-key
OPENAI_API_KEY=test-key
RESEND_API_KEY=test-key
""")

    loader = ConfigLoader(podcasts_yaml, config_yaml, env_file)
    result = loader.load_all()
    assert result is False


def test_invalid_email_format_in_podcasts(temp_dir):
    """Test that invalid email format in podcasts.yaml raises ConfigError."""
    podcasts_yaml = os.path.join(temp_dir, "invalid_podcasts.yaml")
    with open(podcasts_yaml, 'w') as f:
        f.write("""podcasts:
  - name: "Test Podcast"
    slug: "test-podcast"
    rss_url: "https://example.com/feed"
    active: true
    emails:
      - "invalid-email"
""")

    config_yaml = os.path.join(temp_dir, "config.yaml")
    with open(config_yaml, 'w') as f:
        f.write("""settings:
  check_last_n_episodes: 3
  system_email: "admin@example.com"
summary_system_prompt: "System prompt"
summary_default_prompt: "Test prompt"
""")

    env_file = os.path.join(temp_dir, "test.env")
    with open(env_file, 'w') as f:
        f.write("""ASSEMBLYAI_API_KEY=test-key
OPENAI_API_KEY=test-key
RESEND_API_KEY=test-key
""")

    loader = ConfigLoader(podcasts_yaml, config_yaml, env_file)
    result = loader.load_all()
    assert result is False


def test_missing_api_key(temp_dir, monkeypatch):
    """Test that missing API key raises ConfigError."""
    # Clear all API keys from environment to ensure clean state
    monkeypatch.delenv('ASSEMBLYAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('RESEND_API_KEY', raising=False)

    podcasts_yaml = os.path.join(temp_dir, "podcasts.yaml")
    with open(podcasts_yaml, 'w') as f:
        f.write("""podcasts:
  - name: "Test Podcast"
    slug: "test-podcast"
    rss_url: "https://example.com/feed"
    active: true
    emails:
      - "test@example.com"
""")

    config_yaml = os.path.join(temp_dir, "config.yaml")
    with open(config_yaml, 'w') as f:
        f.write("""settings:
  check_last_n_episodes: 3
  system_email: "admin@example.com"
summary_system_prompt: "System prompt"
summary_default_prompt: "Test prompt"
""")

    # Missing ASSEMBLYAI_API_KEY
    env_file = os.path.join(temp_dir, "test.env")
    with open(env_file, 'w') as f:
        f.write("""OPENAI_API_KEY=test-key
RESEND_API_KEY=test-key
""")

    loader = ConfigLoader(podcasts_yaml, config_yaml, env_file)
    result = loader.load_all()
    assert result is False


def test_duplicate_slug_validation(temp_dir):
    """Test that duplicate slugs are caught during validation."""
    podcasts_yaml = os.path.join(temp_dir, "invalid_podcasts.yaml")
    with open(podcasts_yaml, 'w') as f:
        f.write("""podcasts:
  - name: "Podcast 1"
    slug: "test-podcast"
    rss_url: "https://example1.com/feed"
    active: true
  - name: "Podcast 2"
    slug: "test-podcast"
    rss_url: "https://example2.com/feed"
    active: true
""")

    config_yaml = os.path.join(temp_dir, "config.yaml")
    with open(config_yaml, 'w') as f:
        f.write("""settings:
  check_last_n_episodes: 3
  system_email: "admin@example.com"
summary_system_prompt: "System prompt"
summary_default_prompt: "Test prompt"
""")

    env_file = os.path.join(temp_dir, "test.env")
    with open(env_file, 'w') as f:
        f.write("""ASSEMBLYAI_API_KEY=test-key
OPENAI_API_KEY=test-key
RESEND_API_KEY=test-key
""")

    loader = ConfigLoader(podcasts_yaml, config_yaml, env_file)
    result = loader.load_all()
    assert result is False


def test_invalid_system_email(temp_dir):
    """Test that invalid system_email format is caught."""
    podcasts_yaml = os.path.join(temp_dir, "podcasts.yaml")
    with open(podcasts_yaml, 'w') as f:
        f.write("""podcasts:
  - name: "Test Podcast"
    slug: "test-podcast"
    rss_url: "https://example.com/feed"
    active: true
    emails:
      - "test@example.com"
""")

    config_yaml = os.path.join(temp_dir, "config.yaml")
    with open(config_yaml, 'w') as f:
        f.write("""settings:
  check_last_n_episodes: 3
  system_email: "not-an-email"
summary_system_prompt: "System prompt"
summary_default_prompt: "Test prompt"
""")

    env_file = os.path.join(temp_dir, "test.env")
    with open(env_file, 'w') as f:
        f.write("""ASSEMBLYAI_API_KEY=test-key
OPENAI_API_KEY=test-key
RESEND_API_KEY=test-key
""")

    loader = ConfigLoader(podcasts_yaml, config_yaml, env_file)
    result = loader.load_all()
    assert result is False
