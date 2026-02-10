"""Tests for email sending functionality.

As described in PLAN_MASTERPLAN.md:
- Send one real email via Resend API
- Verify email_log has entry for each recipient
- Verify processing_events updated: status='emailed'

Note: These tests require a valid RESEND_API_KEY environment variable.
"""

import pytest


@pytest.mark.integration
@pytest.mark.requires_api_key
def test_send_summary_email(test_db):
    """Integration test: Send summary email via Resend.

    This test requires a valid RESEND_API_KEY in environment and system_email in config.
    Skip this test unless you have API access and want to test real email delivery.
    """
    pytest.skip("Requires valid Resend API key")

    # This is a placeholder showing the expected test flow:
    # from src.emailer import Emailer
    #
    # emailer = Emailer(
    #     system_email="test@example.com",
    #     api_key=os.getenv('RESEND_API_KEY')
    # )
    #
    # # Create test episode with summary
    # test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    # podcast = test_db.get_podcast_by_slug('test-podcast')
    # episode_id = test_db.insert_episode(podcast['id'], {
    #     'guid': 'test-guid',
    #     'title': 'Test Episode',
    #     'link': 'https://example.com/episode',
    #     'image_url': 'https://example.com/image.jpg',
    #     'audio_url': 'https://example.com/audio.mp3'
    # })
    #
    # summary = "This is a test summary of the podcast episode."
    # test_db.update_episode_summary(episode_id, summary)
    #
    # # Send email
    # recipients = ['test@example.com']
    # episode = test_db.get_episode_by_id(episode_id)
    #
    # for recipient in recipients:
    #     if not test_db.email_already_sent(episode_id, recipient):
    #         result = emailer.send_summary(
    #             recipient=recipient,
    #             podcast_name='Test Podcast',
    #             episode_title=episode['title'],
    #             episode_link=episode['link'],
    #             episode_image=episode['image_url'],
    #             summary=summary
    #         )
    #
    #         # Verify email sent successfully
    #         assert result is True
    #
    #         # Log email sent
    #         test_db.log_email_sent(episode_id, recipient)
    #
    # # Verify email log
    # assert test_db.email_already_sent(episode_id, 'test@example.com')
    #
    # # Update processing status
    # test_db.update_processing_status(episode_id, 'emailed')
    #
    # # Verify processing log
    # processing = test_db.get_processing_status(episode_id)
    # assert processing['status'] == 'emailed'


def test_email_already_sent_check(test_db):
    """Test that email_already_sent prevents duplicate sends."""
    # Create test episode
    test_db.sync_podcasts([{'slug': 'test-podcast', 'active': True}])
    podcast = test_db.get_podcast_by_slug('test-podcast')
    episode_id = test_db.insert_episode(podcast['id'], {
        'guid': 'test-guid',
        'title': 'Test Episode',
        'audio_url': 'https://example.com/audio.mp3'
    })

    recipient = 'test@example.com'

    # Initially should not be sent
    assert test_db.email_already_sent(episode_id, recipient) is False

    # Log email as sent
    test_db.log_email_sent(episode_id, recipient)

    # Now should be marked as sent
    assert test_db.email_already_sent(episode_id, recipient) is True
