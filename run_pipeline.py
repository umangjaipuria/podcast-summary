#!/usr/bin/env python3
"""CLI tool for running podcast pipeline stages in isolation.

This tool allows you to run individual pipeline stages for testing,
debugging, or manual processing of podcast episodes.

Usage:
    # Fetch and download latest episode(s)
    uv run run_pipeline.py fetch --podcast tech-podcast --limit 1

    # Contextualize episode metadata
    uv run run_pipeline.py contextualize --episode-id 123

    # Transcribe a specific episode from database
    uv run run_pipeline.py transcribe --episode-id 123

    # Transcribe a specific audio file
    uv run run_pipeline.py transcribe --audio-path ./data/audio/downloaded/episode.mp3

    # Summarize a specific transcript
    uv run run_pipeline.py summarize --episode-id 123
    uv run run_pipeline.py summarize --transcript-path ./data/transcripts/podcast/episode.raw.txt

    # Send email for a specific episode
    uv run run_pipeline.py email --episode-id 123

    # Mark episode as completed and archive audio
    uv run run_pipeline.py complete --episode-id 123

    # Run full pipeline on recent unprocessed episodes
    uv run run_pipeline.py process --podcast tech-podcast
    uv run run_pipeline.py process --podcast tech-podcast --limit 3
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

import click

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
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class PipelineCLI:
    """Pipeline CLI context manager."""

    def __init__(self):
        """Initialize CLI context."""
        self.config_loader = None
        self.db = None
        self.rss_parser = None
        self.downloader = None
        self.contextualizer = None
        self.transcriber = None
        self.summarizer = None
        self.emailer = None

    def initialize(self):
        """Initialize all components."""
        logger.info("Initializing components...")

        # Load configuration
        self.config_loader = ConfigLoader()
        if not self.config_loader.load_all():
            raise click.ClickException("Configuration validation failed")

        # Initialize database
        podcasts_config = self.config_loader.get_podcasts()
        self.db = Database()
        self.db.setup_and_sync(podcasts_config)

        # Initialize components
        settings = self.config_loader.app_config.get('settings', {})
        self.rss_parser = RSSParser(
            max_audio_length_minutes=settings.get('max_audio_length_minutes', 240)
        )
        self.downloader = Downloader(
            max_file_size_mb=settings.get('max_audio_file_size_mb', 500)
        )
        self.contextualizer = Contextualizer()
        self.transcriber = Transcriber(
            api_key=self.config_loader.env_vars['ASSEMBLYAI_API_KEY']
        )
        self.summarizer = Summarizer()
        self.emailer = Emailer(system_email=settings.get('system_email'), reply_to_email=settings.get('reply_to_email'))

        logger.info("Components initialized successfully")

    def cleanup(self):
        """Clean up resources."""
        if self.db:
            self.db.close()

    def get_podcast_config(self, slug):
        """Get podcast configuration by slug."""
        podcasts = self.config_loader.get_podcasts()
        for podcast in podcasts:
            if podcast['slug'] == slug:
                return podcast
        return None

    def get_podcast_by_slug(self, slug):
        """Get podcast database record by slug."""
        return self.db.get_podcast_by_slug(slug)

    def get_episode(self, episode_id):
        """Get episode by ID."""
        return self.db.get_episode_by_id(episode_id)


# Create global context
cli_context = PipelineCLI()


class OrderedGroup(click.Group):
    """Click group that preserves command definition order."""

    def list_commands(self, ctx):
        """Return commands in the order they were added, not alphabetically."""
        return list(self.commands.keys())


@click.group(cls=OrderedGroup)
@click.pass_context
def cli(ctx):
    """Podcast processing pipeline CLI tool.

    Run individual pipeline stages in isolation for testing and debugging.

    \b
    COMMON WORKFLOWS:
    \b
    1. Process latest unprocessed episodes:
       $ uv run run_pipeline.py process --podcast tech-podcast
       $ uv run run_pipeline.py process --podcast tech-podcast --limit 3
    \b
    2. Manually run specific stages on an episode:
       $ uv run run_pipeline.py fetch --podcast tech-podcast
       $ uv run run_pipeline.py contextualize --episode-id 42
       $ uv run run_pipeline.py transcribe --episode-id 42
       $ uv run run_pipeline.py summarize --episode-id 42
       $ uv run run_pipeline.py email --episode-id 42
       $ uv run run_pipeline.py complete --episode-id 42
    \b
    3. Test summarization with custom prompt:
       $ uv run run_pipeline.py summarize --episode-id 42 --prompt "Focus on technical insights"
    \b
    4. Process any audio file directly:
       $ uv run run_pipeline.py transcribe --audio-path ./file.mp3 --podcast tech-podcast

    \b
    FINDING EPISODE IDs:
    \b
    View recent episodes:
      $ sqlite3 data/podcasts.db "SELECT e.id, p.slug, e.title FROM episodes e JOIN podcasts p ON e.podcast_id = p.id ORDER BY e.created_at DESC LIMIT 10;"
    \b
    View episodes for specific podcast:
      $ sqlite3 data/podcasts.db "SELECT e.id, e.title FROM episodes e JOIN podcasts p ON e.podcast_id = p.id WHERE p.slug = 'tech-podcast' ORDER BY e.created_at DESC LIMIT 10;"

    \b
    For detailed help on any command, use:
      $ uv run run_pipeline.py COMMAND --help
    """
    pass


@cli.command()
@click.option('--podcast', required=True, help='Podcast slug from podcasts.yaml')
@click.option('--limit', default=1, type=int, help='Number of episodes to fetch (default: 1)')
@click.option('--download/--no-download', default=True, help='Download audio files (default: yes)')
def fetch(podcast, limit, download):
    """Fetch and optionally download episode(s) from RSS feed.

    This command fetches the latest episode(s) from a podcast's RSS feed,
    creates database entries, and optionally downloads the audio files.

    \b
    Examples:
      # Fetch and download latest episode
      $ uv run run_pipeline.py fetch --podcast tech-podcast

      # Fetch 3 episodes without downloading
      $ uv run run_pipeline.py fetch --podcast tech-podcast --limit 3 --no-download

      # Fetch from different podcast
      $ uv run run_pipeline.py fetch --podcast biz-pod --limit 1
    """
    try:
        cli_context.initialize()

        # Get podcast configuration
        podcast_config = cli_context.get_podcast_config(podcast)
        if not podcast_config:
            raise click.ClickException(f"Podcast '{podcast}' not found in podcasts.yaml")

        # Get or create podcast in database
        podcast_record = cli_context.get_podcast_by_slug(podcast)
        if not podcast_record:
            raise click.ClickException(f"Podcast '{podcast}' not found in database. Run main.py first to sync.")

        logger.info(f"Fetching RSS feed for {podcast}...")
        episodes, podcast_metadata = cli_context.rss_parser.fetch_episodes(
            podcast_config['rss_url'],
            check_last_n=limit
        )

        # Store podcast metadata
        if podcast_metadata:
            cli_context.db.update_podcast_metadata(podcast_record['id'], podcast_metadata)

        if not episodes:
            click.echo(f"No episodes found for {podcast}")
            return

        click.echo(f"\nFound {len(episodes)} episode(s)")

        for i, episode_data in enumerate(episodes, 1):
            episode_title = episode_data.get('title', 'Unknown')
            episode_guid = episode_data['guid']

            click.echo(f"\n{'='*80}")
            click.echo(f"Episode {i}/{len(episodes)}: {episode_title}")
            click.echo(f"{'='*80}")

            # Check if episode exists
            episode = cli_context.db.get_episode_by_guid(episode_guid)
            if episode:
                click.echo(f"✓ Episode already in database (ID: {episode['id']})")
                episode_id = episode['id']
            else:
                # Insert new episode
                episode_id = cli_context.db.insert_episode(podcast_record['id'], episode_data)
                click.echo(f"✓ Created database entry (ID: {episode_id})")

            # Download if requested
            if download:
                # Check if already downloaded
                current_status = cli_context.db.get_current_status(episode_id)
                if current_status in ['downloaded', 'transcribed', 'summarized', 'emailed', 'completed']:
                    click.echo(f"✓ Audio already downloaded (status: {current_status})")
                    continue

                # Download audio
                filename = cli_context.downloader.sanitize_filename(
                    episode_title,
                    episode_data.get('published_date'),
                    episode_guid
                )

                click.echo(f"Downloading audio: {episode_data['audio_url']}")
                audio_path, file_size_mb = cli_context.downloader.download_audio(episode_data['audio_url'], filename)

                if audio_path:
                    click.echo(f"✓ Downloaded to: {audio_path}")

                    # Update file size if available
                    if file_size_mb:
                        cli_context.db.update_episode_file_size(episode_id, file_size_mb)

                    # Log download event
                    cli_context.db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': audio_path})
                else:
                    click.echo("✗ Download failed", err=True)

        click.echo(f"\n{'='*80}")
        click.echo("Fetch complete!")

    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


@cli.command()
@click.option('--episode-id', type=int, required=True, help='Episode ID from database')
def contextualize(episode_id):
    """Generate context from episode metadata.

    Extracts participants, topics, and brief summary from the episode's
    RSS metadata (title, description, date) using an LLM.

    \b
    Examples:
      # Contextualize episode from database
      $ uv run run_pipeline.py contextualize --episode-id 123
    """
    try:
        cli_context.initialize()

        # Get episode
        episode = cli_context.get_episode(episode_id)
        if not episode:
            raise click.ClickException(f"Episode {episode_id} not found")

        # Get podcast info
        podcast_record = cli_context.db.get_podcast_by_id(episode['podcast_id'])
        if not podcast_record:
            raise click.ClickException(f"Podcast not found for episode {episode_id}")

        # Get podcast config
        podcast_config = cli_context.get_podcast_config(podcast_record['slug'])
        if not podcast_config:
            raise click.ClickException(f"Podcast config not found for {podcast_record['slug']}")

        click.echo(f"\nEpisode: {episode['title']}")
        click.echo(f"Podcast: {podcast_config['name']}")

        # Get podcast metadata from database
        import json
        podcast_metadata = {}
        if podcast_record.get('metadata'):
            try:
                podcast_metadata = json.loads(podcast_record['metadata'])
            except (json.JSONDecodeError, TypeError):
                logger.error("Failed to parse podcast metadata from database")

        # Get contextualize prompt
        contextualize_prompt = cli_context.config_loader.get_contextualize_prompt()

        click.echo(f"Generating context...")
        context = cli_context.contextualizer.contextualize_episode(
            podcast_name=podcast_config['name'],
            podcast_author=podcast_metadata.get('author'),
            podcast_description=podcast_metadata.get('description'),
            episode_title=episode['title'],
            published_date=episode.get('published_date'),
            episode_description=episode.get('description'),
            episode_link=episode.get('link'),
            prompt=contextualize_prompt
        )

        if context:
            click.echo(f"✓ Context generated")
            cli_context.db.update_episode_context(episode_id, context)
            cli_context.db.add_processing_event(episode_id, 'contextualized')

            # Print context preview
            click.echo(f"\n{'='*80}")
            click.echo("CONTEXT:")
            click.echo(f"{'='*80}")
            click.echo(context)
        else:
            cli_context.db.add_processing_event(
                episode_id,
                'failed',
                event_data={'error_message': 'Contextualization failed', 'failed_stage': 'contextualize'}
            )
            raise click.ClickException("Contextualization failed")

    except Exception as e:
        # Mark as failed if we have episode_id and database connection
        if episode_id and cli_context.db:
            try:
                current_status = cli_context.db.get_current_status(episode_id)
                failed_stage_map = {
                    None: 'download',
                    'downloaded': 'contextualize',
                    'contextualized': 'transcribe',
                    'transcribed': 'summarize',
                    'summarized': 'email'
                }
                failed_stage = failed_stage_map.get(current_status, 'unknown')
                cli_context.db.add_processing_event(
                    episode_id,
                    'failed',
                    event_data={'error_message': str(e), 'failed_stage': failed_stage}
                )
            except Exception:
                pass  # If we can't update status, just continue with the error
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


@cli.command()
@click.option('--episode-id', type=int, help='Episode ID from database')
@click.option('--audio-path', type=click.Path(exists=True), help='Direct path to audio file')
@click.option('--podcast', help='Podcast slug (required if using --audio-path)')
def transcribe(episode_id, audio_path, podcast):
    """Transcribe an episode or audio file.

    You can either transcribe an episode from the database (using --episode-id)
    or transcribe any audio file directly (using --audio-path and --podcast).

    \b
    Examples:
      # Transcribe episode from database
      $ uv run run_pipeline.py transcribe --episode-id 123

      # Transcribe any audio file directly
      $ uv run run_pipeline.py transcribe --audio-path ./data/audio/downloaded/file.mp3 --podcast tech-podcast

      # Transcribe external audio file
      $ uv run run_pipeline.py transcribe --audio-path /tmp/podcast.mp3 --podcast biz-pod
    """
    try:
        cli_context.initialize()

        if not episode_id and not audio_path:
            raise click.ClickException("Must provide either --episode-id or --audio-path")

        if audio_path and not podcast:
            raise click.ClickException("Must provide --podcast when using --audio-path")

        # Handle direct audio path
        if audio_path:
            audio_path = Path(audio_path).resolve()
            filename = audio_path.stem

            click.echo(f"Transcribing audio file: {audio_path}")
            click.echo(f"Podcast slug: {podcast}")

            transcript_path = cli_context.transcriber.transcribe_audio(
                str(audio_path),
                podcast,
                filename
            )

            if transcript_path:
                click.echo(f"✓ Transcript saved to: {transcript_path}")
            else:
                raise click.ClickException("Transcription failed")

            return

        # Handle episode from database
        episode = cli_context.get_episode(episode_id)
        if not episode:
            raise click.ClickException(f"Episode {episode_id} not found")

        # Get podcast info
        podcast_record = cli_context.db.get_podcast_by_id(episode['podcast_id'])
        if not podcast_record:
            raise click.ClickException(f"Podcast not found for episode {episode_id}")

        click.echo(f"\nEpisode: {episode['title']}")
        click.echo(f"Podcast: {podcast_record['slug']}")

        # Get audio path from latest downloaded event
        download_event_data = cli_context.db.get_event_data(episode_id, 'downloaded')
        if not download_event_data or not download_event_data.get('audio_path'):
            raise click.ClickException(f"No audio file found for episode {episode_id}. Run 'fetch' first.")

        audio_path = download_event_data['audio_path']
        if not Path(audio_path).exists():
            raise click.ClickException(f"Audio file not found: {audio_path}")

        # Move to processing if in downloaded folder
        audio_path_obj = Path(audio_path)
        if audio_path_obj.parent.name == 'downloaded':
            click.echo("Moving audio to processing folder...")
            audio_path = cli_context.downloader.move_to_processing(audio_path)
            cli_context.db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': audio_path})

        # Get filename
        filename = Path(audio_path).stem

        click.echo(f"Transcribing: {audio_path}")
        transcript_path = cli_context.transcriber.transcribe_audio(
            audio_path,
            podcast_record['slug'],
            filename
        )

        if transcript_path:
            click.echo(f"✓ Transcript saved to: {transcript_path}")
            cli_context.db.add_processing_event(episode_id, 'transcribed', event_data={'transcript_path': transcript_path})
        else:
            current_status = cli_context.db.get_current_status(episode_id)
            failed_stage = 'transcribe'
            cli_context.db.add_processing_event(
                episode_id,
                'failed',
                event_data={'error_message': 'Transcription failed', 'failed_stage': failed_stage}
            )
            raise click.ClickException("Transcription failed")

    except Exception as e:
        # Mark as failed if we have episode_id and database connection
        if episode_id and cli_context.db:
            try:
                current_status = cli_context.db.get_current_status(episode_id)
                failed_stage_map = {
                    None: 'download',
                    'downloaded': 'contextualize',
                    'contextualized': 'transcribe',
                    'transcribed': 'summarize',
                    'summarized': 'email'
                }
                failed_stage = failed_stage_map.get(current_status, 'unknown')
                cli_context.db.add_processing_event(
                    episode_id,
                    'failed',
                    event_data={'error_message': str(e), 'failed_stage': failed_stage}
                )
            except Exception:
                pass  # If we can't update status, just continue with the error
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


@cli.command()
@click.option('--episode-id', type=int, help='Episode ID from database')
@click.option('--transcript-path', type=click.Path(exists=True), help='Direct path to transcript file')
@click.option('--podcast', help='Podcast slug (required if using --transcript-path)')
@click.option('--prompt', help='Custom summarization prompt (optional)')
def summarize(episode_id, transcript_path, podcast, prompt):
    """Summarize a transcript.

    You can either summarize a transcript from an episode in the database
    (using --episode-id) or summarize any transcript file directly
    (using --transcript-path and --podcast).

    \b
    Examples:
      # Summarize episode from database
      $ uv run run_pipeline.py summarize --episode-id 123

      # Summarize with custom prompt
      $ uv run run_pipeline.py summarize --episode-id 123 --prompt "Focus on technical insights"

      # Summarize any transcript file
      $ uv run run_pipeline.py summarize --transcript-path ./data/transcripts/podcast/file.raw.txt --podcast tech-podcast

      # Test different prompts
      $ uv run run_pipeline.py summarize --episode-id 123 --prompt "Extract key business decisions and market trends"
    """
    try:
        cli_context.initialize()

        if not episode_id and not transcript_path:
            raise click.ClickException("Must provide either --episode-id or --transcript-path")

        if transcript_path and not podcast:
            raise click.ClickException("Must provide --podcast when using --transcript-path")

        # Get prompt
        if not prompt:
            # Try to get from podcast config
            if podcast:
                podcast_config = cli_context.get_podcast_config(podcast)
                prompt = podcast_config.get('insights_prompt') if podcast_config else None

            # Fall back to default
            if not prompt:
                prompt = cli_context.config_loader.get_default_prompt()

        # Handle direct transcript path
        if transcript_path:
            transcript_path = Path(transcript_path).resolve()
            filename = transcript_path.stem.replace('.raw', '')

            click.echo(f"Summarizing transcript: {transcript_path}")
            click.echo(f"Podcast slug: {podcast}")

            # Get podcast metadata if available
            podcast_metadata = None
            if podcast:
                podcast_record = cli_context.get_podcast_by_slug(podcast)
                if podcast_record and podcast_record.get('metadata'):
                    import json
                    try:
                        podcast_metadata = json.loads(podcast_record['metadata'])
                    except json.JSONDecodeError:
                        pass

            system_prompt = cli_context.config_loader.get_system_prompt()
            summary_path = cli_context.summarizer.summarize_transcript(
                str(transcript_path),
                prompt,
                podcast,
                filename,
                podcast_metadata=podcast_metadata,
                system_prompt=system_prompt
            )

            if summary_path:
                click.echo(f"✓ Summary saved to: {summary_path}")

                # Print summary preview
                with open(summary_path, 'r', encoding='utf-8') as f:
                    summary_text = f.read()
                click.echo(f"\n{'='*80}")
                click.echo("SUMMARY PREVIEW:")
                click.echo(f"{'='*80}")
                click.echo(summary_text[:500] + ("..." if len(summary_text) > 500 else ""))
            else:
                raise click.ClickException("Summarization failed")

            return

        # Handle episode from database
        episode = cli_context.get_episode(episode_id)
        if not episode:
            raise click.ClickException(f"Episode {episode_id} not found")

        # Get podcast info
        podcast_record = cli_context.db.get_podcast_by_id(episode['podcast_id'])
        if not podcast_record:
            raise click.ClickException(f"Podcast not found for episode {episode_id}")

        click.echo(f"\nEpisode: {episode['title']}")
        click.echo(f"Podcast: {podcast_record['slug']}")

        # Get transcript path from latest transcribed event
        transcribe_event_data = cli_context.db.get_event_data(episode_id, 'transcribed')
        if not transcribe_event_data or not transcribe_event_data.get('transcript_path'):
            raise click.ClickException(f"No transcript found for episode {episode_id}. Run 'transcribe' first.")

        transcript_path = transcribe_event_data['transcript_path']
        if not Path(transcript_path).exists():
            raise click.ClickException(f"Transcript file not found: {transcript_path}")

        # Get filename
        filename = Path(transcript_path).stem.replace('.raw', '')

        # Get prompt from podcast config if not provided
        if not prompt:
            podcast_config = cli_context.get_podcast_config(podcast_record['slug'])
            if podcast_config:
                prompt = podcast_config.get('insights_prompt', cli_context.config_loader.get_default_prompt())

        # Get context from database
        context = episode.get('context')

        # Get podcast metadata from database
        podcast_metadata = None
        if podcast_record.get('metadata'):
            import json
            try:
                podcast_metadata = json.loads(podcast_record['metadata'])
            except json.JSONDecodeError:
                pass

        # Get system prompt from config
        system_prompt = cli_context.config_loader.get_system_prompt()

        click.echo(f"Summarizing: {transcript_path}")
        summary_path = cli_context.summarizer.summarize_transcript(
            transcript_path,
            prompt,
            podcast_record['slug'],
            filename,
            context=context,
            podcast_metadata=podcast_metadata,
            system_prompt=system_prompt
        )

        if summary_path:
            click.echo(f"✓ Summary saved to: {summary_path}")

            # Read and save summary to database
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary_text = f.read()
            cli_context.db.update_episode_summary(episode_id, summary_text)
            cli_context.db.add_processing_event(episode_id, 'summarized', event_data={'summary_path': summary_path})

            # Print summary preview
            click.echo(f"\n{'='*80}")
            click.echo("SUMMARY PREVIEW:")
            click.echo(f"{'='*80}")
            click.echo(summary_text[:500] + ("..." if len(summary_text) > 500 else ""))
        else:
            cli_context.db.add_processing_event(
                episode_id,
                'failed',
                event_data={'error_message': 'Summarization failed', 'failed_stage': 'summarize'}
            )
            raise click.ClickException("Summarization failed")

    except Exception as e:
        # Mark as failed if we have episode_id and database connection
        if episode_id and cli_context.db:
            try:
                current_status = cli_context.db.get_current_status(episode_id)
                failed_stage_map = {
                    None: 'download',
                    'downloaded': 'contextualize',
                    'contextualized': 'transcribe',
                    'transcribed': 'summarize',
                    'summarized': 'email'
                }
                failed_stage = failed_stage_map.get(current_status, 'unknown')
                cli_context.db.add_processing_event(
                    episode_id,
                    'failed',
                    event_data={'error_message': str(e), 'failed_stage': failed_stage}
                )
            except Exception:
                pass  # If we can't update status, just continue with the error
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


@cli.command()
@click.option('--episode-id', type=int, required=True, help='Episode ID from database')
@click.option('--recipients', help='Comma-separated email addresses (overrides config)')
@click.option('--output', type=click.Path(), help='Write HTML to file instead of sending email')
def email(episode_id, recipients, output):
    """Send summary email for an episode.

    Sends the episode summary via email to configured recipients or
    to specified email addresses. Can also generate HTML preview file.

    \b
    Examples:
      # Send to configured recipients
      $ uv run run_pipeline.py email --episode-id 123

      # Send to custom recipients
      $ uv run run_pipeline.py email --episode-id 123 --recipients user@example.com

      # Send to multiple recipients
      $ uv run run_pipeline.py email --episode-id 123 --recipients user@example.com,other@example.com

      # Generate HTML preview without sending
      $ uv run run_pipeline.py email --episode-id 123 --output preview.html
    """
    try:
        cli_context.initialize()

        # Get episode
        episode = cli_context.get_episode(episode_id)
        if not episode:
            raise click.ClickException(f"Episode {episode_id} not found")

        # Get podcast info
        podcast_record = cli_context.db.get_podcast_by_id(episode['podcast_id'])
        if not podcast_record:
            raise click.ClickException(f"Podcast not found for episode {episode_id}")

        # Get podcast config
        podcast_config = cli_context.get_podcast_config(podcast_record['slug'])
        if not podcast_config:
            raise click.ClickException(f"Podcast config not found for {podcast_record['slug']}")

        click.echo(f"\nEpisode: {episode['title']}")
        click.echo(f"Podcast: {podcast_config['name']}")

        # Get summary
        if not episode.get('generated_summary'):
            raise click.ClickException(f"No summary found for episode {episode_id}. Run 'summarize' first.")

        summary_text = episode['generated_summary']

        # If output file specified, generate HTML and write to file
        if output:
            click.echo(f"Generating HTML preview...")

            # Generate HTML using emailer's internal method
            html_body = cli_context.emailer._build_html_body(
                episode_title=episode['title'],
                episode_link=episode['link'],
                image_url=episode.get('image_url'),
                summary=summary_text
            )

            # Write to file
            with open(output, 'w', encoding='utf-8') as f:
                f.write(html_body)

            click.echo(f"✓ HTML written to: {output}")
            return

        # Get recipients
        if recipients:
            recipient_list = [r.strip() for r in recipients.split(',')]
        else:
            recipient_list = podcast_config.get('emails', [])

        if not recipient_list:
            raise click.ClickException("No recipients specified. Use --recipients or configure emails in podcasts.yaml")

        click.echo(f"Recipients: {', '.join(recipient_list)}")

        # Get podcast image URL and link from metadata for fallback
        import json
        podcast_image_url = None
        podcast_link = None
        if podcast_record.get('metadata'):
            try:
                metadata = json.loads(podcast_record['metadata'])
                podcast_image_url = metadata.get('image_url')
                podcast_link = metadata.get('link')
            except json.JSONDecodeError:
                pass

        # Send emails
        all_sent = True
        html_content = None
        for recipient in recipient_list:
            # Check if already sent
            if cli_context.db.email_already_sent(episode_id, recipient):
                click.echo(f"⊙ Email already sent to {recipient}")
                continue

            # Send email
            success, html_content = cli_context.emailer.send_summary_email(
                podcast_name=podcast_config['name'],
                episode_title=episode['title'],
                episode_link=episode['link'],
                image_url=episode.get('image_url'),
                summary=summary_text,
                recipients=[recipient],
                podcast_image_url=podcast_image_url,
                podcast_link=podcast_link,
                duration_minutes=episode.get('duration_minutes'),
                published_date=episode.get('published_date')
            )

            if success:
                cli_context.db.log_email_sent(episode_id, recipient)
                click.echo(f"✓ Email sent to {recipient}")
            else:
                click.echo(f"✗ Failed to send email to {recipient}", err=True)
                all_sent = False

        if all_sent:
            cli_context.db.add_processing_event(
                episode_id,
                'emailed',
                event_data={'recipients': recipient_list},
                additional_details=html_content
            )
            click.echo("\n✓ All emails sent successfully")
        else:
            click.echo("\n⚠ Some emails failed to send", err=True)

    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


@cli.command()
@click.option('--episode-id', type=int, required=True, help='Episode ID from database')
def complete(episode_id):
    """Mark episode as completed and move audio to archive.

    Use this after manually running individual pipeline stages to finalize
    the episode and clean up audio files.

    \b
    Examples:
      # Mark episode as complete and archive audio
      $ uv run run_pipeline.py complete --episode-id 123

    \b
    This command will:
      - Mark the episode status as 'completed' in the database
      - Move the audio file from processing/downloaded to archive folder
    """
    try:
        cli_context.initialize()

        # Get episode
        episode = cli_context.get_episode(episode_id)
        if not episode:
            raise click.ClickException(f"Episode {episode_id} not found")

        # Get podcast info
        podcast_record = cli_context.db.get_podcast_by_id(episode['podcast_id'])
        if not podcast_record:
            raise click.ClickException(f"Podcast not found for episode {episode_id}")

        click.echo(f"\nEpisode: {episode['title']}")
        click.echo(f"Podcast: {podcast_record['slug']}")

        # Get audio path from latest downloaded event
        download_event_data = cli_context.db.get_event_data(episode_id, 'downloaded')
        if not download_event_data:
            raise click.ClickException(f"No processing record found for episode {episode_id}")

        # Mark as completed
        cli_context.db.add_processing_event(episode_id, 'completed')
        click.echo("✓ Episode marked as completed")

        # Archive audio if it exists
        audio_path = download_event_data.get('audio_path')
        if audio_path and Path(audio_path).exists():
            cli_context.downloader.move_to_archive(audio_path)
            click.echo(f"✓ Audio moved to archive: {audio_path}")
        elif audio_path:
            click.echo(f"⚠ Audio file not found (may already be archived): {audio_path}")
        else:
            click.echo("⚠ No audio path recorded for this episode")

    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


@cli.command()
@click.option('--podcast', required=True, help='Podcast slug from podcasts.yaml')
@click.option('--limit', default=1, type=int, help='Number of recent episodes to process (default: 1)')
def process(podcast, limit):
    """Run full pipeline for recent unprocessed episodes.

    Fetches recent episodes from RSS feed and runs the complete pipeline
    (download → contextualize → transcribe → summarize → email) for any unprocessed episodes.

    Use individual commands (contextualize, transcribe, summarize, email) if you need to
    run specific stages in isolation.

    \b
    Examples:
      # Process latest unprocessed episode
      $ uv run run_pipeline.py process --podcast tech-podcast

      # Process up to 3 recent episodes (skips already downloaded)
      $ uv run run_pipeline.py process --podcast tech-podcast --limit 3
    """
    try:
        cli_context.initialize()

        # Always run all stages
        stage_list = ['download', 'contextualize', 'transcribe', 'summarize', 'email']

        # Get podcast configuration
        podcast_config = cli_context.get_podcast_config(podcast)
        if not podcast_config:
            raise click.ClickException(f"Podcast '{podcast}' not found in podcasts.yaml")

        # Get podcast from database
        podcast_record = cli_context.get_podcast_by_slug(podcast)
        if not podcast_record:
            raise click.ClickException(f"Podcast '{podcast}' not found in database. Run main.py first to sync.")

        # Fetch recent episodes from RSS
        logger.info(f"Fetching RSS feed for {podcast}...")
        episodes, podcast_metadata = cli_context.rss_parser.fetch_episodes(
            podcast_config['rss_url'],
            check_last_n=limit
        )

        # Store podcast metadata
        if podcast_metadata:
            cli_context.db.update_podcast_metadata(podcast_record['id'], podcast_metadata)

        if not episodes:
            click.echo(f"No episodes found for {podcast}")
            return

        # Filter to only unprocessed episodes
        episodes_to_process = []
        for episode_data in episodes:
            episode_guid = episode_data['guid']
            episode = cli_context.db.get_episode_by_guid(episode_guid)

            if episode:
                # Check if already downloaded
                current_status = cli_context.db.get_current_status(episode['id'])
                if current_status in ['downloaded', 'contextualized', 'transcribed', 'summarized', 'emailed', 'completed']:
                    logger.info(f"Skipping already processed episode: {episode_data.get('title', 'Unknown')} (status: {current_status})")
                    continue
                episodes_to_process.append((episode['id'], episode_data))
            else:
                # Create new episode in database
                episode_id = cli_context.db.insert_episode(podcast_record['id'], episode_data)
                episodes_to_process.append((episode_id, episode_data))

        if not episodes_to_process:
            click.echo(f"No unprocessed episodes found for {podcast}")
            return

        click.echo(f"\nFound {len(episodes_to_process)} episode(s) to process")
        click.echo(f"Stages: {', '.join(stage_list)}\n")

        # Process each episode
        for idx, (episode_id, episode_data) in enumerate(episodes_to_process, 1):
            click.echo(f"\n{'='*80}")
            click.echo(f"Processing episode {idx}/{len(episodes_to_process)}")
            click.echo(f"{'='*80}")

            try:
                episode = cli_context.get_episode(episode_id)
                if not episode:
                    click.echo(f"✗ Episode {episode_id} not found, skipping", err=True)
                    continue

                click.echo(f"Episode: {episode['title']}")
                click.echo(f"Podcast: {podcast_config['name']}")
                click.echo(f"Stages: {', '.join(stage_list)}\n")

                # Get current processing data from events
                download_event_data = cli_context.db.get_event_data(episode_id, 'downloaded')
                transcribe_event_data = cli_context.db.get_event_data(episode_id, 'transcribed')
                audio_path = download_event_data.get('audio_path') if download_event_data else None
                transcript_path = transcribe_event_data.get('transcript_path') if transcribe_event_data else None

                # Track summary across stages to avoid stale episode data
                summary_text = episode.get('generated_summary')

                # Stage 1: Download
                if 'download' in stage_list:
                    click.echo("Stage 1: Downloading audio...")

                    if audio_path and Path(audio_path).exists():
                        click.echo(f"✓ Audio already downloaded: {audio_path}")
                    else:
                        filename = cli_context.downloader.sanitize_filename(
                            episode['title'],
                            episode.get('published_date'),
                            episode['episode_guid']
                        )

                        audio_path, file_size_mb = cli_context.downloader.download_audio(episode['audio_url'], filename)
                        if not audio_path:
                            raise click.ClickException("Failed to download audio")

                        click.echo(f"✓ Downloaded to: {audio_path}")

                        # Update file size if available
                        if file_size_mb:
                            cli_context.db.update_episode_file_size(episode_id, file_size_mb)

                        cli_context.db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': audio_path})

                # Stage 2: Contextualize
                if 'contextualize' in stage_list:
                    click.echo("\nStage 2: Contextualizing episode...")

                    if episode.get('context'):
                        click.echo("✓ Context already generated")
                    else:
                        contextualize_prompt = cli_context.config_loader.get_contextualize_prompt()
                        podcast_config = cli_context.get_podcast_config(podcast_record['slug'])

                        # Use metadata from RSS fetch (already stored in DB)
                        # Fall back to reading from DB if not available
                        metadata = podcast_metadata
                        if not metadata and podcast_record.get('metadata'):
                            import json
                            try:
                                metadata = json.loads(podcast_record['metadata'])
                            except (json.JSONDecodeError, TypeError):
                                metadata = {}

                        context = cli_context.contextualizer.contextualize_episode(
                            podcast_name=podcast_config['name'],
                            podcast_author=metadata.get('author'),
                            podcast_description=metadata.get('description'),
                            episode_title=episode['title'],
                            published_date=episode.get('published_date'),
                            episode_description=episode.get('description'),
                            episode_link=episode.get('link'),
                            prompt=contextualize_prompt
                        )

                        if not context:
                            raise click.ClickException("Failed to generate context")

                        cli_context.db.update_episode_context(episode_id, context)
                        cli_context.db.add_processing_event(episode_id, 'contextualized')
                        click.echo("✓ Context generated")

                # Stage 3: Transcribe
                if 'transcribe' in stage_list:
                    click.echo("\nStage 3: Transcribing audio...")

                    if not audio_path:
                        raise click.ClickException("No audio file available. Run with 'download' stage first.")

                    if transcript_path and Path(transcript_path).exists():
                        click.echo(f"✓ Transcript already exists: {transcript_path}")
                    else:
                        # Move to processing if needed
                        audio_path_obj = Path(audio_path)
                        if audio_path_obj.parent.name == 'downloaded':
                            audio_path = cli_context.downloader.move_to_processing(audio_path)
                            cli_context.db.add_processing_event(episode_id, 'downloaded', event_data={'audio_path': audio_path})

                        filename = Path(audio_path).stem
                        transcript_path = cli_context.transcriber.transcribe_audio(
                            audio_path,
                            podcast_record['slug'],
                            filename
                        )

                        if not transcript_path:
                            raise click.ClickException("Failed to transcribe audio")

                        click.echo(f"✓ Transcript saved to: {transcript_path}")
                        cli_context.db.add_processing_event(episode_id, 'transcribed', event_data={'transcript_path': transcript_path})

                # Stage 4: Summarize
                if 'summarize' in stage_list:
                    click.echo("\nStage 4: Summarizing transcript...")

                    if not transcript_path:
                        raise click.ClickException("No transcript available. Run with 'transcribe' stage first.")

                    if summary_text:
                        click.echo("✓ Summary already exists")
                    else:
                        filename = Path(transcript_path).stem.replace('.raw', '')
                        prompt = podcast_config.get('insights_prompt', cli_context.config_loader.get_default_prompt())

                        # Get context from database
                        context = episode.get('context')

                        # Get system prompt from config
                        system_prompt = cli_context.config_loader.get_system_prompt()

                        summary_path = cli_context.summarizer.summarize_transcript(
                            transcript_path,
                            prompt,
                            podcast_record['slug'],
                            filename,
                            context=context,
                            podcast_metadata=podcast_metadata,
                            system_prompt=system_prompt
                        )

                        if not summary_path:
                            raise click.ClickException("Failed to generate summary")

                        with open(summary_path, 'r', encoding='utf-8') as f:
                            summary_text = f.read()

                        cli_context.db.update_episode_summary(episode_id, summary_text)
                        cli_context.db.add_processing_event(episode_id, 'summarized', event_data={'summary_path': summary_path})
                        click.echo(f"✓ Summary saved to: {summary_path}")

                # Stage 5: Email
                if 'email' in stage_list:
                    click.echo("\nStage 5: Sending emails...")

                    if not summary_text:
                        raise click.ClickException("No summary available. Run with 'summarize' stage first.")

                    recipients = podcast_config.get('emails', [])

                    if not recipients:
                        click.echo("⚠ No recipients configured in podcasts.yaml, skipping email")
                    else:
                        # Get podcast image URL and link from metadata for fallback
                        podcast_image_url = podcast_metadata.get('image_url') if podcast_metadata else None
                        podcast_link = podcast_metadata.get('link') if podcast_metadata else None

                        all_sent = True
                        html_content = None
                        for recipient in recipients:
                            if cli_context.db.email_already_sent(episode_id, recipient):
                                click.echo(f"⊙ Email already sent to {recipient}")
                                continue

                            success, html_content = cli_context.emailer.send_summary_email(
                                podcast_name=podcast_config['name'],
                                episode_title=episode['title'],
                                episode_link=episode['link'],
                                image_url=episode.get('image_url'),
                                summary=summary_text,
                                recipients=[recipient],
                                podcast_image_url=podcast_image_url,
                                podcast_link=podcast_link,
                                duration_minutes=episode.get('duration_minutes'),
                                published_date=episode.get('published_date')
                            )

                            if success:
                                cli_context.db.log_email_sent(episode_id, recipient)
                                click.echo(f"✓ Email sent to {recipient}")
                            else:
                                click.echo(f"✗ Failed to send email to {recipient}", err=True)
                                all_sent = False

                        if all_sent:
                            cli_context.db.add_processing_event(
                                episode_id,
                                'emailed',
                                event_data={'recipients': recipients},
                                additional_details=html_content
                            )

                # Mark as completed if all stages were run
                if set(stage_list) == {'download', 'contextualize', 'transcribe', 'summarize', 'email'}:
                    cli_context.db.add_processing_event(episode_id, 'completed')

                    # Archive audio
                    if audio_path:
                        cli_context.downloader.move_to_archive(audio_path)
                        click.echo(f"\n✓ Audio moved to archive")

                click.echo(f"✓ Episode {idx}/{len(episodes_to_process)} completed successfully")

            except Exception as e:
                # Mark as failed for this episode
                click.echo(f"\n✗ Episode {idx}/{len(episodes_to_process)} failed: {str(e)}", err=True)
                try:
                    current_status = cli_context.db.get_current_status(episode_id)
                    failed_stage_map = {
                        None: 'download',
                        'downloaded': 'contextualize',
                        'contextualized': 'transcribe',
                        'transcribed': 'summarize',
                        'summarized': 'email'
                    }
                    failed_stage = failed_stage_map.get(current_status, 'unknown')
                    cli_context.db.add_processing_event(
                        episode_id,
                        'failed',
                        event_data={'error_message': str(e), 'failed_stage': failed_stage}
                    )
                except Exception:
                    pass  # If we can't update status, just continue
                # Continue with next episode instead of failing entire batch
                continue

        click.echo(f"\n{'='*80}")
        click.echo("All episodes processed!")
        click.echo(f"{'='*80}")

    except Exception as e:
        raise click.ClickException(str(e))
    finally:
        cli_context.cleanup()


if __name__ == '__main__':
    cli()
