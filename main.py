#!/usr/bin/env python3
"""Main orchestrator for podcast monitoring and summarization."""

import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.config_loader import ConfigLoader
from src.database import Database
from src.rss_parser import RSSParser
from src.downloader import Downloader
from src.contextualizer import Contextualizer
from src.transcriber import Transcriber
from src.summarizer import Summarizer
from src.emailer import Emailer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Main execution workflow."""
    logger.info("=" * 45)
    logger.info("Podcast Monitor Starting")
    logger.info("=" * 45)

    # Step 1: Load and validate configurations
    logger.info("Step 1: Loading and validating configurations...")
    config_loader = ConfigLoader()

    if not config_loader.load_all():
        logger.error("Configuration validation failed. Exiting.")
        return 1

    podcasts_config = config_loader.get_podcasts()
    default_prompt = config_loader.get_default_prompt()
    system_prompt = config_loader.get_system_prompt()
    contextualize_prompt = config_loader.get_contextualize_prompt()

    # Get settings
    check_last_n_episodes = config_loader.get_setting('check_last_n_episodes', 3)
    max_episode_age_days = config_loader.get_setting('max_episode_age_days', 3)
    max_audio_length_minutes = config_loader.get_setting('max_audio_length_minutes', 240)
    max_audio_file_size_mb = config_loader.get_setting('max_audio_file_size_mb', 500)
    system_email = config_loader.get_setting('system_email')

    # Step 2: Initialize database and sync podcasts
    logger.info("Step 2: Initializing database...")
    db = Database()
    db.setup_and_sync(podcasts_config)

    # Initialize components
    rss_parser = RSSParser(max_audio_length_minutes=max_audio_length_minutes)
    downloader = Downloader(max_file_size_mb=max_audio_file_size_mb)
    contextualizer = Contextualizer()
    transcriber = Transcriber(api_key=config_loader.env_vars['ASSEMBLYAI_API_KEY'])
    summarizer = Summarizer()
    emailer = Emailer(system_email=system_email, reply_to_email=config_loader.get_setting('reply_to_email'))

    # Create podcast lookup for quick access
    podcast_lookup = {p['slug']: p for p in podcasts_config}

    # Step 3: Process each active podcast
    logger.info("Step 3: Processing active podcasts...")
    active_podcasts = db.get_active_podcasts()
    logger.info(f"Found {len(active_podcasts)} active podcasts")

    has_failures = False
    for podcast in active_podcasts:
        try:
            process_podcast(
                podcast=podcast,
                podcast_config=podcast_lookup.get(podcast['slug']),
                db=db,
                rss_parser=rss_parser,
                downloader=downloader,
                contextualizer=contextualizer,
                transcriber=transcriber,
                summarizer=summarizer,
                emailer=emailer,
                check_last_n_episodes=check_last_n_episodes,
                max_episode_age_days=max_episode_age_days,
                default_prompt=default_prompt,
                system_prompt=system_prompt,
                contextualize_prompt=contextualize_prompt
            )
        except Exception as e:
            logger.error(f"Error processing podcast {podcast['slug']}: {e}")
            has_failures = True
            continue

    # Step 6: Clean up failed episodes
    logger.info("Step 6: Cleaning up failed episodes...")
    cleanup_failed_episodes(db, downloader)

    # Step 7: Send error summary email
    logger.info("Step 7: Sending error summary email...")
    send_error_summary(db, emailer, system_email)

    # Close database connection
    db.close()

    logger.info("=" * 45)
    if has_failures:
        logger.error("Podcast Monitor Completed with failures")
        logger.info("=" * 45)
        return 1
    else:
        logger.info("Podcast Monitor Completed successfully")
        logger.info("=" * 45)
        return 0


def process_podcast(podcast, podcast_config, db, rss_parser, downloader,
                   contextualizer, transcriber, summarizer, emailer, check_last_n_episodes,
                   max_episode_age_days, default_prompt, system_prompt, contextualize_prompt):
    """Process a single podcast.

    Args:
        podcast: Podcast database record
        podcast_config: Podcast configuration from podcasts.yaml
        db: Database instance
        rss_parser: RSSParser instance
        downloader: Downloader instance
        contextualizer: Contextualizer instance
        transcriber: Transcriber instance
        summarizer: Summarizer instance
        emailer: Emailer instance
        check_last_n_episodes: Number of episodes to check
        max_episode_age_days: Skip episodes older than this (in days)
        default_prompt: Default summarization prompt
        system_prompt: System prompt for LLM
        contextualize_prompt: Default contextualize prompt
    """
    slug = podcast['slug']
    logger.info(f"Processing podcast: {slug}")

    # Fetch RSS feed
    logger.info(f"Fetching RSS feed for {slug}...")
    episodes, podcast_metadata = rss_parser.fetch_episodes(
        podcast_config['rss_url'],
        check_last_n=check_last_n_episodes
    )

    # Update last_checked timestamp and metadata after successful fetch
    db.update_podcast_last_checked(podcast['id'])
    if podcast_metadata:
        db.update_podcast_metadata(podcast['id'], podcast_metadata)

    if not episodes:
        logger.warning(f"No episodes found for {slug}")
        return

    logger.info(f"Found {len(episodes)} episodes for {slug}")

    # Process each episode
    for episode_data in episodes:
        try:
            process_episode(
                episode_data=episode_data,
                podcast=podcast,
                podcast_config=podcast_config,
                podcast_metadata=podcast_metadata,
                db=db,
                downloader=downloader,
                contextualizer=contextualizer,
                transcriber=transcriber,
                summarizer=summarizer,
                emailer=emailer,
                max_episode_age_days=max_episode_age_days,
                default_prompt=default_prompt,
                system_prompt=system_prompt,
                contextualize_prompt=contextualize_prompt
            )
        except Exception as e:
            logger.error(f"Error processing episode {episode_data.get('title', 'Unknown')}: {e}")
            # Propagate failure up to main - this stops processing other episodes in this podcast
            # but allows other podcasts to continue (handled by try/except in main loop)
            raise


def process_episode(episode_data, podcast, podcast_config, podcast_metadata, db, downloader,
                   contextualizer, transcriber, summarizer, emailer, max_episode_age_days,
                   default_prompt, system_prompt, contextualize_prompt):
    """Process a single episode through the full pipeline.

    Args:
        episode_data: Episode data from RSS parser
        podcast: Podcast database record
        podcast_config: Podcast configuration from podcasts.yaml
        podcast_metadata: Podcast metadata from RSS feed (description, author, link)
        db: Database instance
        downloader: Downloader instance
        contextualizer: Contextualizer instance
        transcriber: Transcriber instance
        summarizer: Summarizer instance
        emailer: Emailer instance
        max_episode_age_days: Skip episodes older than this (in days)
        default_prompt: Default summarization prompt
        system_prompt: System prompt for LLM
        contextualize_prompt: Default contextualize prompt
    """
    episode_guid = episode_data['guid']
    episode_title = episode_data.get('title', 'Unknown')

    # Check if episode already exists
    episode = db.get_episode_by_guid(episode_guid)
    if episode:
        logger.info(f"Episode already exists: {episode_title}")
        episode_id = episode['id']

        # Check if already processed
        current_status = db.get_current_status(episode_id)
        if current_status:
            logger.info(f"Episode already in processing log with status: {current_status}")
            return
    else:
        # Insert new episode
        logger.info(f"New episode: {episode_title}")
        episode_id = db.insert_episode(podcast['id'], episode_data)

    # Check if we should process this episode
    if not podcast_config.get('emails'):
        logger.info(f"No emails configured for {podcast['slug']}, skipping processing")
        return

    # Final backstop: Check episode age limit
    published_date_str = episode_data.get('published_date')
    if published_date_str:
        try:
            published_date = datetime.fromisoformat(published_date_str.replace('Z', '+00:00'))
            # Remove timezone info for comparison (compare dates only)
            published_date = published_date.replace(tzinfo=None)
            now = datetime.now()
            age_days = (now - published_date).days

            if age_days > max_episode_age_days:
                logger.warning(
                    f"Skipping episode '{episode_title}': "
                    f"published {age_days} days ago, exceeds limit {max_episode_age_days} days"
                )
                return
        except (ValueError, AttributeError) as e:
            # If we can't parse the date, process the episode optimistically
            logger.debug(f"Could not parse published date for age check: {e}")

    # Start processing
    try:
        # Create filename
        filename = downloader.sanitize_filename(
            episode_title,
            episode_data.get('published_date'),
            episode_guid
        )
        base_filename = Path(filename).stem

        # Step 4: Download audio
        logger.info(f"Downloading audio for: {episode_title}")
        audio_path, file_size_mb = downloader.download_audio(episode_data['audio_url'], filename)

        if not audio_path:
            raise Exception("Failed to download audio")

        # Update file size if we got it from download (more accurate than RSS)
        if file_size_mb:
            db.update_episode_file_size(episode_id, file_size_mb)

        # Log download event
        db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': audio_path})

        # Step 4.5: Contextualize episode using metadata
        logger.info(f"Contextualizing episode: {episode_title}")
        context = contextualizer.contextualize_episode(
            podcast_name=podcast_config['name'],
            podcast_author=podcast_metadata.get('author'),
            podcast_description=podcast_metadata.get('description'),
            episode_title=episode_title,
            published_date=episode_data.get('published_date'),
            episode_description=episode_data.get('description'),
            episode_link=episode_data.get('link'),
            prompt=contextualize_prompt
        )

        if not context:
            raise Exception("Failed to generate context")

        # Save context to database
        db.update_episode_context(episode_id, context)
        db.add_processing_event(episode_id, 'contextualized')

        # Step 5: Move to processing and transcribe
        logger.info(f"Transcribing episode: {episode_title}")
        audio_path = downloader.move_to_processing(audio_path)

        transcript_path = transcriber.transcribe_audio(
            audio_path,
            podcast['slug'],
            base_filename
        )

        if not transcript_path:
            raise Exception("Failed to transcribe audio")

        db.add_processing_event(episode_id, 'transcribed', event_data={'transcript_path': transcript_path})

        # Summarize
        logger.info(f"Summarizing episode: {episode_title}")
        prompt = podcast_config.get('insights_prompt', default_prompt)

        # Get context from database
        episode_with_context = db.get_episode_by_id(episode_id)
        context = episode_with_context.get('context') if episode_with_context else None

        summary_path = summarizer.summarize_transcript(
            transcript_path,
            prompt,
            podcast['slug'],
            base_filename,
            context=context,
            podcast_metadata=podcast_metadata,
            system_prompt=system_prompt
        )

        if not summary_path:
            raise Exception("Failed to generate summary")

        # Read summary and update database
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary_text = f.read()
        db.update_episode_summary(episode_id, summary_text)
        db.add_processing_event(episode_id, 'summarized', event_data={'summary_path': summary_path})

        # Send emails
        logger.info(f"Sending emails for: {episode_title}")
        recipients = podcast_config.get('emails', [])
        episode = db.get_episode_by_id(episode_id)

        # Get podcast image URL and link from metadata for fallback
        podcast_image_url = podcast_metadata.get('image_url') if podcast_metadata else None
        podcast_link = podcast_metadata.get('link') if podcast_metadata else None

        all_emails_sent = True
        html_content = None
        for recipient in recipients:
            # Skip if already sent
            if db.email_already_sent(episode_id, recipient):
                logger.info(f"Email already sent to {recipient}")
                continue

            # Send email
            success, html_content = emailer.send_summary_email(
                podcast_name=podcast_config['name'],
                episode_title=episode['title'],
                episode_link=episode['link'],
                image_url=episode['image_url'],
                summary=summary_text,
                recipients=[recipient],
                podcast_image_url=podcast_image_url,
                podcast_link=podcast_link,
                duration_minutes=episode.get('duration_minutes'),
                published_date=episode.get('published_date')
            )

            if success:
                db.log_email_sent(episode_id, recipient)
            else:
                all_emails_sent = False

        # Only mark as emailed if all emails were sent successfully
        if not all_emails_sent:
            raise Exception("Failed to send one or more emails")

        # Log email event with recipients and HTML content
        db.add_processing_event(
            episode_id,
            'emailed',
            event_data={'recipients': recipients},
            additional_details=html_content
        )

        # Mark as completed
        db.add_processing_event(episode_id, 'completed')

        # Move to archive
        downloader.move_to_archive(audio_path)

        logger.info(f"Successfully processed episode: {episode_title}")

    except Exception as e:
        # Mark as failed
        error_message = str(e)
        logger.error(f"Failed to process episode {episode_title}: {error_message}")
        # Determine which stage failed based on current status
        current_status = db.get_current_status(episode_id)
        failed_stage_map = {
            None: 'download',
            'downloaded': 'contextualize',
            'contextualized': 'transcribe',
            'transcribed': 'summarize',
            'summarized': 'email'
        }
        failed_stage = failed_stage_map.get(current_status, 'unknown')
        db.add_processing_event(
            episode_id,
            'failed',
            event_data={'error_message': error_message, 'failed_stage': failed_stage}
        )


def cleanup_failed_episodes(db, downloader):
    """Clean up audio files for failed episodes.

    Args:
        db: Database instance
        downloader: Downloader instance
    """
    # Get ALL failed episodes for cleanup (not just recent ones)
    failed_episodes = db.get_failed_episodes(hours=None)

    if not failed_episodes:
        logger.info("No failed episodes to clean up")
        return

    logger.info(f"Cleaning up {len(failed_episodes)} failed episodes...")

    for failed in failed_episodes:
        episode_title = failed.get('episode_title', 'Unknown')
        audio_path = failed.get('audio_path')

        if audio_path:
            try:
                downloader.delete_audio_file(audio_path)
                logger.info(f"Cleaned up audio for failed episode: {episode_title}")
            except Exception as e:
                logger.error(f"Error cleaning up {episode_title}: {e}")
        else:
            logger.debug(f"No audio path for failed episode: {episode_title}")


def send_error_summary(db, emailer, system_email):
    """Send error summary email to system admin.

    Args:
        db: Database instance
        emailer: Emailer instance
        system_email: Admin email address
    """
    failed_episodes = db.get_failed_episodes()

    if not failed_episodes:
        logger.info("No failed episodes to report")
        return

    logger.info(f"Sending error summary for {len(failed_episodes)} failed episodes")
    emailer.send_error_summary_email(failed_episodes, system_email)


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(2)
