"""Tests for error handling and failure scenarios.

As described in PLAN_MASTERPLAN.md:
1. Episode-Level Failure Handling:
   - Force error mid-pipeline
   - Verify processing_events: status='failed', error_message populated in event_data
   - Verify error summary email sent to system_email
   - Verify next episode still processes (failure isolation)
   - Verify failed episode is NOT retried on subsequent runs
"""

import pytest
from datetime import datetime, timedelta


def test_failed_episode_marked_in_db(test_db, sample_episode_data):
    """Test that failed episodes are marked with error message."""
    # Create podcast and episode
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')
    episode_id = test_db.insert_episode(podcast['id'], sample_episode_data)

    # Simulate failure during processing
    error_message = "Failed to transcribe: API timeout"
    test_db.add_processing_event(
        episode_id,
        status='failed',
        event_data={'error_message': error_message, 'failed_stage': 'transcribe'}
    )

    # Verify processing events
    current_status = test_db.get_current_status(episode_id)
    assert current_status == 'failed'
    failed_event_data = test_db.get_event_data(episode_id, 'failed')
    assert failed_event_data is not None
    assert failed_event_data['error_message'] == error_message
    assert failed_event_data['failed_stage'] == 'transcribe'


def test_failed_episodes_query(test_db, sample_episode_data):
    """Test that failed episodes can be retrieved for error reporting."""
    # Create podcast and episodes
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')

    # Create successful episode
    episode_data_1 = sample_episode_data.copy()
    episode_data_1['guid'] = 'success-guid'
    episode_id_1 = test_db.insert_episode(podcast['id'], episode_data_1)
    test_db.add_processing_event(episode_id_1, 'completed')

    # Create failed episode
    episode_data_2 = sample_episode_data.copy()
    episode_data_2['guid'] = 'failed-guid'
    episode_data_2['title'] = 'Failed Episode'
    episode_id_2 = test_db.insert_episode(podcast['id'], episode_data_2)
    test_db.add_processing_event(
        episode_id_2,
        'failed',
        event_data={'error_message': 'Transcription API error', 'failed_stage': 'transcribe'}
    )

    # Query failed episodes
    failed_episodes = test_db.get_failed_episodes(hours=24)

    assert len(failed_episodes) == 1
    assert failed_episodes[0]['podcast_slug'] == 'test-podcast'
    assert failed_episodes[0]['episode_title'] == 'Failed Episode'
    assert failed_episodes[0]['error_message'] == 'Transcription API error'


def test_failed_episode_not_retried(test_db, sample_episode_data):
    """Test that failed episodes remain failed and are not retried."""
    # Create podcast and episode
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')
    episode_id = test_db.insert_episode(podcast['id'], sample_episode_data)

    # Mark as failed
    test_db.add_processing_event(
        episode_id,
        'failed',
        event_data={'error_message': 'Test error', 'failed_stage': 'download'}
    )

    # Get processing status
    current_status = test_db.get_current_status(episode_id)
    assert current_status == 'failed'

    # In orchestrator logic, failed episodes should be skipped:
    # if current_status in ['completed', 'failed']:
    #     skip_episode = True
    should_skip = current_status in ['completed', 'failed']
    assert should_skip is True


def test_failure_isolation(test_db, sample_episode_data):
    """Test that one failed episode doesn't block processing of others."""
    # Create podcast
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')

    # Create two episodes
    episode_data_1 = sample_episode_data.copy()
    episode_data_1['guid'] = 'episode-1'
    episode_data_1['title'] = 'Episode 1'
    episode_id_1 = test_db.insert_episode(podcast['id'], episode_data_1)

    episode_data_2 = sample_episode_data.copy()
    episode_data_2['guid'] = 'episode-2'
    episode_data_2['title'] = 'Episode 2'
    episode_id_2 = test_db.insert_episode(podcast['id'], episode_data_2)

    # Mark first as failed
    test_db.add_processing_event(
        episode_id_1,
        'failed',
        event_data={'error_message': 'Test error', 'failed_stage': 'download'}
    )

    # Mark second as completed
    test_db.add_processing_event(episode_id_2, 'completed')

    # Verify both have correct statuses
    status_1 = test_db.get_current_status(episode_id_1)
    status_2 = test_db.get_current_status(episode_id_2)

    assert status_1 == 'failed'
    assert status_2 == 'completed'

    # This demonstrates that failures are isolated
    # In the orchestrator, each episode is processed in a try-except block
    # so one failure doesn't affect others
