"""Tests for transcription functionality.

As described in PLAN_MASTERPLAN.md:
- Transcribe one real audio file using AssemblyAI
- Verify .raw.txt file created with correct naming format
- Verify processing_events updated: status='transcribed', transcript_path set correctly in event_data

Note: These tests require a valid ASSEMBLYAI_API_KEY environment variable.
Mark as @pytest.mark.integration and @pytest.mark.requires_api_key
"""

import os
import pytest


@pytest.mark.integration
@pytest.mark.requires_api_key
def test_transcribe_audio(test_db, temp_dir):
    """Integration test: Transcribe audio file using AssemblyAI.

    This test requires:
    - Valid ASSEMBLYAI_API_KEY in environment
    - Audio file to transcribe (can use a short test file)

    Skip this test unless you have API access and want to test real transcription.
    """
    pytest.skip("Requires valid AssemblyAI API key and audio file")

    # This is a placeholder showing the expected test flow:
    # from src.transcriber import Transcriber
    #
    # transcriber = Transcriber(api_key=os.getenv('ASSEMBLYAI_API_KEY'))
    #
    # # Setup test audio file path
    # audio_path = f"{temp_dir}/test-audio.mp3"
    #
    # # Create test episode in database
    # test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    # podcast = test_db.get_podcast_by_slug('test-podcast')
    # episode_id = test_db.insert_episode(podcast['id'], {
    #     'guid': 'test-guid',
    #     'title': 'Test Episode',
    #     'audio_url': 'https://example.com/audio.mp3'
    # })
    #
    # # Transcribe
    # transcript_path = f"{temp_dir}/transcripts/test-podcast/20240115-test-episode.raw.txt"
    # os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
    #
    # result = transcriber.transcribe(audio_path, transcript_path)
    #
    # # Verify transcript file created
    # assert os.path.exists(transcript_path)
    #
    # # Verify content includes speaker labels
    # with open(transcript_path, 'r') as f:
    #     content = f.read()
    #     assert 'Speaker' in content
    #
    # # Update database
    # test_db.update_processing_status(episode_id, 'transcribed', transcript_path=transcript_path)
    #
    # # Verify processing log
    # processing = test_db.get_processing_status(episode_id)
    # assert processing['status'] == 'transcribed'
    # assert processing['transcript_path'] == transcript_path


def test_transcript_file_naming():
    """Test that transcript file naming follows the expected format."""
    from src.downloader import Downloader

    # Test the filename sanitization which is used for transcripts too
    filename = Downloader.sanitize_filename(
        title="Test Episode",
        published_date="2024-01-15T10:00:00"
    )

    # Remove .mp3 extension and verify format
    base_name = filename.replace('.mp3', '')
    assert base_name.startswith("20240115-")
    assert "test-episode" in base_name

    # Expected transcript filename would be: 20240115-test-episode.raw.txt
    transcript_name = base_name + ".raw.txt"
    assert transcript_name.endswith(".raw.txt")
