"""Tests for summarization functionality.

As described in PLAN_MASTERPLAN.md:
- Summarize one real transcript using LLM
- Test with custom podcast prompt
- Test with default prompt
- Verify episodes.generated_summary column populated
- Verify processing_events updated: status='summarized'

Note: These tests require valid LLM API keys (OPENAI_API_KEY or GEMINI_API_KEY).
"""

import os
import pytest


@pytest.mark.integration
@pytest.mark.requires_api_key
def test_summarize_with_custom_prompt(test_db, sample_transcript, temp_dir):
    """Integration test: Summarize transcript with custom prompt.

    This test requires a valid LLM API key (OpenAI or Google Gemini).
    Skip this test unless you have API access.
    """
    pytest.skip("Requires valid LLM API key")

    # This is a placeholder showing the expected test flow:
    # from src.summarizer import Summarizer
    #
    # summarizer = Summarizer()
    #
    # # Create test episode
    # test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    # podcast = test_db.get_podcast_by_slug('test-podcast')
    # episode_id = test_db.insert_episode(podcast['id'], {
    #     'guid': 'test-guid',
    #     'title': 'Test Episode',
    #     'audio_url': 'https://example.com/audio.mp3'
    # })
    #
    # # Custom prompt
    # custom_prompt = "Focus on technical insights and key takeaways"
    #
    # # Generate summary
    # summary = summarizer.summarize(sample_transcript, custom_prompt)
    #
    # # Verify summary generated
    # assert summary is not None
    # assert len(summary) > 0
    #
    # # Save to database
    # test_db.update_episode_summary(episode_id, summary)
    #
    # # Verify database updated
    # episode = test_db.get_episode_by_id(episode_id)
    # assert episode['generated_summary'] == summary
    #
    # # Update processing status
    # summary_path = f"{temp_dir}/transcripts/test-podcast/20240115-test-episode.summary.txt"
    # test_db.update_processing_status(episode_id, 'summarized', summary_path=summary_path)
    #
    # # Verify processing log
    # processing = test_db.get_processing_status(episode_id)
    # assert processing['status'] == 'summarized'
    # assert processing['summary_path'] == summary_path


@pytest.mark.integration
@pytest.mark.requires_api_key
def test_summarize_with_default_prompt(test_config_loader, sample_transcript):
    """Integration test: Summarize transcript with default prompt."""
    pytest.skip("Requires valid LLM API key")

    # This is a placeholder showing the expected test flow:
    # from src.summarizer import Summarizer
    #
    # test_config_loader.load_all()
    # default_prompt = test_config_loader.get_default_prompt()
    #
    # summarizer = Summarizer()
    # summary = summarizer.summarize(sample_transcript, default_prompt)
    #
    # assert summary is not None
    # assert len(summary) > 0


def test_summary_file_naming():
    """Test that summary file naming follows the expected format."""
    from src.downloader import Downloader

    # Test the filename sanitization
    filename = Downloader.sanitize_filename(
        title="Test Episode",
        published_date="2024-01-15T10:00:00"
    )

    # Expected summary filename: 20240115-test-episode.summary.txt
    base_name = filename.replace('.mp3', '')
    summary_name = base_name + ".summary.txt"

    assert summary_name.startswith("20240115-")
    assert summary_name.endswith(".summary.txt")
    assert "test-episode" in summary_name
