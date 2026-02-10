"""Tests for idempotency and duplicate handling.

As described in PLAN_MASTERPLAN.md:
- Run download twice → episode not re-inserted (GUID deduplication)
- Episode already in processing_events → skip processing
- Email already sent (in email_log) → don't re-send
"""

import pytest


def test_episode_guid_deduplication(test_db, sample_episode_data):
    """Test that episodes are deduplicated by GUID."""
    # Create podcast
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')

    # Insert episode first time
    episode_id_1 = test_db.insert_episode(podcast['id'], sample_episode_data)
    assert episode_id_1 > 0

    # Check episode exists
    assert test_db.episode_exists(sample_episode_data['guid']) is True

    # Try to insert same episode again (should fail due to unique GUID constraint)
    with pytest.raises(Exception):  # Should raise sqlite3.IntegrityError
        test_db.insert_episode(podcast['id'], sample_episode_data)

    # Verify only one episode exists
    episode = test_db.get_episode_by_guid(sample_episode_data['guid'])
    assert episode is not None
    assert episode['id'] == episode_id_1


def test_processing_log_prevents_reprocessing(test_db, sample_episode_data):
    """Test that episodes already in processing_events are not reprocessed."""
    # Create podcast and episode
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')
    episode_id = test_db.insert_episode(podcast['id'], sample_episode_data)

    # Check processing status (should be None initially)
    current_status = test_db.get_current_status(episode_id)
    assert current_status is None

    # Mark as downloaded
    test_db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': '/tmp/test.mp3'})

    # Check processing status again
    current_status = test_db.get_current_status(episode_id)
    assert current_status == 'downloaded'

    # In the actual orchestrator, this would skip reprocessing
    # We simulate that check here
    if current_status in ['completed', 'failed']:
        skip_processing = True
    else:
        skip_processing = False

    # Since status is 'downloaded', it should continue processing
    assert skip_processing is False

    # Mark as completed
    test_db.add_processing_event(episode_id, 'completed')

    # Now check again
    current_status = test_db.get_current_status(episode_id)
    if current_status in ['completed', 'failed']:
        skip_processing = True
    else:
        skip_processing = False

    # Since status is 'completed', it should skip reprocessing
    assert skip_processing is True


def test_email_deduplication(test_db, sample_episode_data):
    """Test that emails are not sent twice to same recipient."""
    # Create podcast and episode
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')
    episode_id = test_db.insert_episode(podcast['id'], sample_episode_data)

    recipient = 'test@example.com'

    # Initially should not be sent
    assert test_db.email_already_sent(episode_id, recipient) is False

    # Simulate email sending logic
    if not test_db.email_already_sent(episode_id, recipient):
        # Send email (mocked)
        # emailer.send(...)
        # Log as sent
        test_db.log_email_sent(episode_id, recipient)

    # Verify logged
    assert test_db.email_already_sent(episode_id, recipient) is True

    # Try to send again
    if not test_db.email_already_sent(episode_id, recipient):
        pytest.fail("Should not attempt to send email again")

    # Verify still only one log entry
    assert test_db.email_already_sent(episode_id, recipient) is True
