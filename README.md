# Podcast Summaries

An automated system that monitors podcast RSS feeds, transcribes new episodes with speaker diarization, generates AI-powered summaries, and delivers them via email. Designed for personal use on a low-end VPS with daily execution via systemd timer.

## Overview

This system automates the entire workflow of staying up-to-date with your favorite podcasts:

1. **RSS Monitoring**: Daily checks of configured podcast RSS feeds
2. **Episode Download**: Automatically downloads new episodes
3. **Metadata Contextualization**: Extracts participants, topics, and episode summary from RSS metadata using Gemini 2.5 Flash
4. **Transcription**: Uses AssemblyAI for high-quality transcription with speaker diarization
5. **AI Summarization**: Generates concise summaries using OpenAI GPT or Google Gemini (enhanced with context from step 3)
6. **Email Delivery**: Sends formatted summaries to configured recipients via Resend

### Key Features

- **Automated Daily Execution**: Runs via systemd timer (default: 5 AM Pacific Time daily)
- **Intelligent Deduplication**: Tracks processed episodes to avoid re-processing
- **Custom Prompts**: Configure different summarization prompts per podcast
- **Multi-recipient Support**: Send summaries to different email lists per podcast
- **Resource-Efficient**: Designed for low-end VPS with SQLite database
- **Robust Error Handling**: Failed episodes are tracked; system sends error summaries to admin
- **Configurable Limits**: Set max episode length, file size, and retention periods

### Architecture

```
┌─────────────────────────────────────┐
│   Daily Systemd Timer (5 AM PT)     │
└────────────────┬────────────────────┘
                 │
    ┌────────────▼────────────┐
    │  Main Orchestrator      │
    └────────────┬────────────┘
                 │
    ┌────────────┼────────────┬────────────┐
    │            │            │            │
┌───▼───┐  ┌─────▼──────┐ ┌──▼────┐  ┌───▼────┐
│  RSS  │  │Contextualize│ │Trans- │  │  LLM   │
│Parser │─►│  Metadata  │─►│ cribe │─►│Summary │
└───┬───┘  └────────────┘ └───────┘  └───┬────┘
    │                                     │
    ▼                                     ▼
┌──────────┐                        ┌──────────┐
│  SQLite  │                        │  Email   │
│ Database │                        │ Service  │
└──────────┘                        └──────────┘
```

## Setup Instructions (New VPS)

### Prerequisites

- Ubuntu 20.04+ or Debian 11+ (or similar Linux distribution)
- Minimum 2GB RAM, 20GB disk space
- Root or sudo access
- Domain with email sending capabilities (for Resend)

### Required API Keys

You'll need accounts and API keys for:

1. **AssemblyAI** - https://www.assemblyai.com/ ($0.15/hour for transcription)
2. **OpenAI** or **Google Gemini** - For AI summarization
3. **Resend** - https://resend.com/ (Email delivery)

### Step 1: Initial System Setup
Note: this assumes the system already has git and homebrew installed

#### Install uv via Homebrew
```bash
brew install uv
```

### Step 2: Clone and Setup Project

#### Set up github deploy key (if it doesn't exist)
```bash
# Generate SSH key for GitHub
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_githubdeploy_podcastsummary -C "github deploy key for podcast-summary"

# Add to SSH config
cat >> ~/.ssh/config <<EOF
Host github-podcastsummary
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_githubdeploy_podcastsummary
  IdentitiesOnly yes
EOF

# Copy public key and add to GitHub
cat ~/.ssh/id_ed25519_githubdeploy_podcastsummary.pub
# Go to GitHub repo → Settings → Deploy keys → Add deploy key (paste public key)

# Clone repository
```bash
cd /home/<USER>
git clone git@github-podcastsummary:<GITHUB_USERNAME>/podcast-summary.git
cd podcast-summary
```

##### Create Python virtual environment and install dependencies
``` bash
uv sync
```

### Step 3: Configure Environment Variables

```bash
# Copy example env file
cp dotenv.example .env

# Edit .env with your API keys
nano .env
```

Add your API keys to `.env`:

```bash
# API Keys
ASSEMBLYAI_API_KEY=<YOUR_ASSEMBLYAI_API_KEY>
OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>             # OR use Gemini
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>             # OR use OpenAI
RESEND_API_KEY=<YOUR_RESEND_API_KEY>
```

**Note**: Right now you need both `OPENAI_API_KEY` and `GEMINI_API_KEY`, because it uses GPT 5 Mini for contextualization and Gemini 3 Pro for summarization. You can easily change this in the code to using only one provider.

### Step 4: Configure Podcasts and Settings

#### Edit `podcasts.yaml`

```bash
nano podcasts.yaml
```

Add your podcast subscriptions:

```yaml
podcasts:
  - name: "Your Favorite Podcast"
    slug: "favorite-podcast"                      # Unique ID for file paths
    rss_url: "https://feeds.example.com/podcast"  # RSS feed URL
    active: true                                  # Set to false to disable
    emails:
      - "your.email@example.com"
    insights_prompt: "Focus on technical insights and key takeaways"
```

#### Edit `config.yaml`

```bash
nano config.yaml
```

Update system settings (especially `system_email`):

```yaml
settings:
  check_last_n_episodes: 1             # How many recent episodes to check
  max_audio_length_minutes: 240         # Skip episodes longer than 4 hours
  archive_retention_days: 15            # Delete old audio files after 15 days
  max_audio_file_size_mb: 500           # Max file size to download
  max_transcript_retention_days: 365    # Keep transcripts for 1 year
  system_email: "admin@example.com"  # Sender address for emails AND error notifications
```

### Step 5: Test the System

```bash
# Run manually to test
uv run main.py
```

Check the output for any errors. The first run will:
- Create `data/` directory structure
- Initialize SQLite database
- Fetch RSS feeds
- Download, transcribe, and summarize episodes
- Send emails

### Step 6: Setup Systemd Timer for Daily Execution

The systemd timer runs the podcast summary automatically at 5 AM Pacific Time daily.

**Requirements**: systemd v228+ (released Nov 2015). Check your version with `systemctl --version`.

#### Initial Installation

```bash
# Copy service files to systemd directory
sudo cp deployment/podcast-summary.service /etc/systemd/system/
sudo cp deployment/podcast-summary.timer /etc/systemd/system/

# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable and start the timer (this enables it to start on boot)
sudo systemctl enable podcast-summary.timer
sudo systemctl start podcast-summary.timer

# Verify timer is active
sudo systemctl status podcast-summary.timer
```

#### Updating After Configuration Changes

If you modify systemd files in `deployment/`, you need to reinstall them:

```bash
# Copy updated files
sudo cp deployment/podcast-summary.service /etc/systemd/system/
sudo cp deployment/podcast-summary.timer /etc/systemd/system/

# Reload systemd configuration
sudo systemctl daemon-reload

# Restart the timer to apply changes
sudo systemctl restart podcast-summary.timer

# Verify changes took effect
sudo systemctl status podcast-summary.timer
```

**Note**: You only need to restart the timer, not the service itself. The timer controls when the service runs.

#### Listing All Timers

```bash
# List all active timers
sudo systemctl list-timers

# List all timers including inactive ones
sudo systemctl list-timers --all

# Filter for podcast-related timers
sudo systemctl list-timers --all | grep podcast
```

### Step 7: Verify the System is Working

#### Check Timer Status

```bash
# View timer status and next scheduled run
sudo systemctl status podcast-summary.timer

# Sample output shows:
# - Whether timer is active
# - When it last ran (Trigger)
# - When it will run next (Triggers)
```

#### Check Service Logs

```bash
# View logs from most recent run
sudo journalctl -u podcast-summary.service -n 100

# Follow live logs (useful during manual testing)
sudo journalctl -u podcast-summary.service -f

# View logs from today only
sudo journalctl -u podcast-summary.service --since today

# View logs from last 24 hours
sudo journalctl -u podcast-summary.service --since "24 hours ago"

# View logs with timestamps
sudo journalctl -u podcast-summary.service --since today --no-pager
```

#### Manual Test Run

To test the service immediately without waiting for the timer:

```bash
# Run the service manually (bypasses timer)
sudo systemctl start podcast-summary.service

# Check if it completed successfully
sudo systemctl status podcast-summary.service

# View the logs from that run
sudo journalctl -u podcast-summary.service -n 200
```

#### Check Service Exit Status

The service reports its completion status to systemd and healthchecks.io:

```bash
# Check the last exit code
systemctl show podcast-summary.service -p ExecMainStatus

# Output meanings:
# ExecMainStatus=0  → Success (all episodes processed)
# ExecMainStatus=1  → Partial failure (some episodes failed, but script completed)
# ExecMainStatus=2  → Fatal error (script crashed)
```

#### Verify Timer Schedule

```bash
# Show next scheduled run time
systemctl list-timers podcast-summary.timer

# Show detailed timer configuration
systemctl cat podcast-summary.timer
```

#### Common Verification Checks

```bash
# 1. Is the timer enabled?
systemctl is-enabled podcast-summary.timer
# Should output: enabled

# 2. Is the timer active?
systemctl is-active podcast-summary.timer
# Should output: active

# 3. When will it run next?
systemctl list-timers podcast-summary.timer
# Shows: NEXT (next run), LEFT (time until next run)

# 4. Did the last run succeed?
systemctl status podcast-summary.service
# Look for: "code=exited, status=0/SUCCESS"
```

### Step 8: (Optional) Setup Healthchecks.io Monitoring

The service already includes healthchecks.io integration (the UUID is hardcoded in the service file). The service will:
- Ping healthchecks.io when starting
- Report success (exit code 0) or failure (non-zero) when complete

1. Create account at https://healthchecks.io/
2. Create a new check with 24-hour interval
3. Copy the check UUID
4. Edit the service file to update the UUID:

```bash
sudo nano /etc/systemd/system/podcast-summary.service
```

Update the `HEALTHCHECKS_UUID` environment variable:

```ini
Environment="HEALTHCHECKS_UUID=<YOUR_HEALTHCHECKS_UUID>"
```

5. Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart podcast-summary.timer
```

## Project Structure

```
podcast-summary/
├── main.py                      # Main orchestrator
├── pyproject.toml              # Python dependencies (uv format)
├── podcasts.yaml               # Podcast subscriptions
├── config.yaml                 # Application settings
├── .env                        # API keys and secrets (not in git)
├── dotenv.example              # Example .env template
├── src/
│   ├── config_loader.py        # Load and validate configs
│   ├── rss_parser.py           # Fetch & parse RSS feeds
│   ├── database.py             # SQLite operations
│   ├── downloader.py           # Download audio files
│   ├── contextualizer.py       # Extract metadata context with Gemini
│   ├── transcriber.py          # Transcription with AssemblyAI
│   ├── summarizer.py           # LLM orchestrator
│   ├── llm/
│   │   ├── openai.py           # OpenAI GPT provider
│   │   └── gemini.py           # Google Gemini provider
│   └── emailer.py              # Send emails via Resend
├── deployment/
│   ├── podcast-summary.service # Systemd service unit
│   └── podcast-summary.timer   # Systemd timer unit
├── scripts/                    # Utility scripts (if needed)
└── data/                       # Created on first run
    ├── podcasts.db             # SQLite database
    ├── audio/
    │   ├── downloaded/         # Freshly downloaded files
    │   ├── processing/         # Currently being transcribed
    │   └── archive/            # Completed files
    └── transcripts/
        └── {podcast-slug}/     # Organized by podcast
            ├── *.raw.txt       # Raw transcripts
            └── *.summary.txt   # Generated summaries
```

## Configuration Guide

### podcasts.yaml

Configure which podcasts to monitor:

```yaml
podcasts:
  - name: "Podcast Display Name"
    slug: "unique-slug"                           # REQUIRED: used for file paths
    rss_url: "https://example.com/feed.xml"       # REQUIRED: RSS feed URL
    active: true                                  # REQUIRED: false to disable
    emails:                                       # OPTIONAL: if omitted, episode is skipped
      - "recipient1@example.com"
      - "recipient2@example.com"
    insights_prompt: "Custom summary instructions" # OPTIONAL: uses default if omitted
```

**Required fields**: `name`, `slug`, `rss_url`, `active`
**Optional fields**: `emails`, `insights_prompt`

### config.yaml

Application-wide settings:

- **check_last_n_episodes**: How many recent episodes to check per RSS feed
- **max_audio_length_minutes**: Skip episodes longer than this (saves transcription costs)
- **archive_retention_days**: Auto-delete old audio files after this many days
- **max_audio_file_size_mb**: Skip downloading files larger than this
- **system_email**: Admin email for error notifications

## Maintenance

### View Logs

```bash
# Follow live logs
sudo journalctl -u podcast-summary.service -f

# View last run
sudo journalctl -u podcast-summary.service --since "1 day ago"

# View database
sqlite3 data/podcasts.db "SELECT * FROM episodes ORDER BY created_at DESC LIMIT 10;"
```

### Manual Execution

```bash
cd ~/podcast-summary
uv run main.py
```

### Running Pipeline Stages in Isolation

The `run_pipeline.py` CLI tool allows you to run individual pipeline stages for testing, debugging, or manual processing. This is useful when you want to:
- Process a specific episode through one or more stages
- Test transcription/summarization on a single episode
- Re-process a failed episode
- Debug issues with specific stages

#### Available Commands

The pipeline includes these stages in order:
1. **fetch** - Download episodes from RSS feed
2. **contextualize** - Extract metadata context (participants, topics)
3. **transcribe** - Transcribe audio with speaker diarization
4. **summarize** - Generate AI summary
5. **email** - Send summary via email
6. **complete** - Mark as done and archive audio
7. **process** - Run full pipeline automatically

```bash
# View all available commands
uv run python run_pipeline.py --help

# View help for a specific command
uv run python run_pipeline.py fetch --help
```

#### 1. Fetch Episodes

Fetch the latest episode(s) from a podcast's RSS feed and optionally download the audio:

```bash
# Fetch and download latest episode from a podcast
uv run python run_pipeline.py fetch --podcast tech-podcast --limit 1

# Fetch 3 episodes without downloading (creates DB entries only)
uv run python run_pipeline.py fetch --podcast tech-podcast --limit 3 --no-download
```

**Options:**
- `--podcast`: Podcast slug from `podcasts.yaml` (required)
- `--limit`: Number of episodes to fetch (default: 1)
- `--download/--no-download`: Whether to download audio files (default: yes)

#### 2. Contextualize Episodes

Extract metadata context (participants, topics, episode summary) from RSS information:

```bash
# Contextualize an episode from the database
uv run python run_pipeline.py contextualize --episode-id 123
```

This step uses Gemini 2.5 Flash with automatic thinking mode to extract structured context from episode metadata. The context is later passed to the summarizer to improve summary quality.

**Options:**
- `--episode-id`: Episode ID from database (required)

**Note**: This step requires the episode to exist in the database (run `fetch` first). Podcast metadata (description, author) is automatically extracted from the RSS feed and stored in the database.

#### 3. Transcribe Episodes

Transcribe a specific episode or audio file:

```bash
# Transcribe an episode from the database
uv run python run_pipeline.py transcribe --episode-id 123

# Transcribe any audio file directly
uv run python run_pipeline.py transcribe --audio-path ./data/audio/downloaded/episode.mp3 --podcast tech-podcast
```

**Options:**
- `--episode-id`: Episode ID from database
- `--audio-path`: Direct path to audio file
- `--podcast`: Podcast slug (required when using `--audio-path`)

#### 4. Summarize Transcripts

Generate a summary from a transcript:

```bash
# Summarize an episode from the database
uv run python run_pipeline.py summarize --episode-id 123

# Summarize any transcript file directly
uv run python run_pipeline.py summarize --transcript-path ./data/transcripts/podcast/episode.raw.txt --podcast tech-podcast

# Use a custom prompt
uv run python run_pipeline.py summarize --episode-id 123 --prompt "Focus on technical details and code examples"
```

**Options:**
- `--episode-id`: Episode ID from database
- `--transcript-path`: Direct path to transcript file
- `--podcast`: Podcast slug (required when using `--transcript-path`)
- `--prompt`: Custom summarization prompt (optional, uses podcast or default prompt otherwise)

**Note**: If the episode was contextualized in step 2, the summary will automatically include that context for better results.

#### 5. Send Emails

Send summary email for a processed episode, or generate HTML preview:

```bash
# Send to configured recipients
uv run python run_pipeline.py email --episode-id 123

# Send to specific recipients (overrides config)
uv run python run_pipeline.py email --episode-id 123 --recipients user@example.com,other@example.com

# Generate HTML preview without sending email
uv run python run_pipeline.py email --episode-id 123 --output preview.html
```

**Options:**
- `--episode-id`: Episode ID from database (required)
- `--recipients`: Comma-separated email addresses (optional, uses podcast config by default)
- `--output`: Write HTML to file instead of sending email (useful for previewing formatting)

#### 6. Mark Episode as Complete

Mark an episode as completed and move audio to archive:

```bash
# Mark episode as complete and archive audio
uv run python run_pipeline.py complete --episode-id 123
```

This is useful after manually running individual stages (fetch, transcribe, summarize, email) to finalize the episode and clean up audio files.

**Options:**
- `--episode-id`: Episode ID from database (required)

#### 7. Process Complete Pipeline

Run the full pipeline for recent unprocessed episodes:

```bash
# Process latest unprocessed episode from a podcast
uv run python run_pipeline.py process --podcast tech-podcast

# Process up to 3 recent unprocessed episodes
uv run python run_pipeline.py process --podcast tech-podcast --limit 3
```

This command automatically runs all stages (download → contextualize → transcribe → summarize → email → complete) for episodes that haven't been processed yet.

**Options:**
- `--podcast`: Podcast slug from podcasts.yaml (required)
- `--limit`: Number of recent episodes to process (default: 1)

#### Example Workflows

**Workflow 1: Manual step-by-step processing**

```bash
# Step 1: Fetch the latest episode (creates DB entry and downloads audio)
uv run python run_pipeline.py fetch --podcast tech-podcast --limit 1

# Note the episode ID from the output (e.g., "Created database entry (ID: 42)")

# Step 2: Contextualize episode metadata
uv run python run_pipeline.py contextualize --episode-id 42

# Step 3: Transcribe the episode
uv run python run_pipeline.py transcribe --episode-id 42

# Step 4: Generate summary (includes context from step 2)
uv run python run_pipeline.py summarize --episode-id 42

# Step 5: Preview email (optional)
uv run python run_pipeline.py email --episode-id 42 --output preview.html

# Step 6: Send email
uv run python run_pipeline.py email --episode-id 42

# Step 7: Mark as complete and archive audio
uv run python run_pipeline.py complete --episode-id 42
```

**Workflow 2: Using process command (automatic)**

```bash
# Run all stages together for recent unprocessed episodes
uv run python run_pipeline.py process --podcast tech-podcast

# Process up to 3 recent episodes
uv run python run_pipeline.py process --podcast tech-podcast --limit 3
```

#### Finding Episode IDs

To find episode IDs in the database:

```bash
# View recent episodes
sqlite3 data/podcasts.db "SELECT e.id, p.slug, e.title FROM episodes e JOIN podcasts p ON e.podcast_id = p.id ORDER BY e.created_at DESC LIMIT 10;"

# View episodes for a specific podcast
sqlite3 data/podcasts.db "SELECT e.id, e.title, e.published_date FROM episodes e JOIN podcasts p ON e.podcast_id = p.id WHERE p.slug = 'tech-podcast' ORDER BY e.published_date DESC LIMIT 10;"

# View processing status
sqlite3 data/podcasts.db "SELECT e.id, e.title, pl.status FROM episodes e LEFT JOIN processing_log pl ON e.id = pl.episode_id ORDER BY e.created_at DESC LIMIT 10;"
```

### Backup Database

Database backups should be done manually using standard file copy commands:

```bash
# Create a timestamped backup
cp data/podcasts.db data/podcasts.db.$(date +%Y%m%d_%H%M%S).backup

# Or simple backup
cp data/podcasts.db data/podcasts.db.backup
```

### Cleanup Old Files

Archive cleanup should be done manually. Old audio files in `data/audio/archive/` can be removed based on the retention policy in `config.yaml`:

```bash
# View files older than 15 days (adjust as needed)
find data/audio/archive -type f -mtime +15

# Remove files older than 15 days
find data/audio/archive -type f -mtime +15 -delete

# Remove old transcripts (e.g., older than 365 days)
find data/transcripts -type f -name "*.txt" -mtime +365 -delete
```

### Change Execution Schedule

Edit the timer unit:

```bash
sudo nano /etc/systemd/system/podcast-summary.timer
```

Change `OnCalendar=*-*-* 05:00:00 America/Los_Angeles` to your preferred time and timezone. You can use:
- IANA timezone names: `America/Los_Angeles`, `Europe/London`, `Asia/Tokyo`
- UTC: `*-*-* 13:00:00 UTC`
- Or omit timezone to use the server's local timezone

```bash
# List available timezones
timedatectl list-timezones

# Test your calendar specification
systemd-analyze calendar "*-*-* 05:00:00 America/Los_Angeles"

# Apply changes
sudo systemctl daemon-reload
sudo systemctl restart podcast-summary.timer
```

## Testing

The project includes comprehensive tests as described in `PLAN_MASTERPLAN.md`. Tests are organized into unit tests, integration tests, and end-to-end tests.

### Test Structure

The test suite includes:
- **Configuration Validation Tests** - Verify config loading and validation
- **Download Tests** - Test RSS parsing and audio download
- **Transcription Tests** - Test AssemblyAI integration (requires API key)
- **Summarization Tests** - Test LLM integration (requires API key)
- **Email Tests** - Test Resend email delivery (requires API key)
- **Idempotency Tests** - Verify duplicate handling and deduplication
- **End-to-End Tests** - Full pipeline tests (requires all API keys)
- **Error Handling Tests** - Test failure scenarios and recovery

### Running Tests

#### Install Test Dependencies

```bash
# Install development dependencies including pytest
uv sync --extra dev
```

#### Run All Tests (Unit Tests Only)

```bash
# Run tests that don't require API keys or network access
uv run pytest -m "not integration and not requires_api_key and not e2e"
```

#### Run All Tests Including Integration Tests

```bash
# Run all tests (requires internet access, may download RSS feeds)
uv run pytest
```

#### Run Specific Test Files

```bash
# Run only configuration validation tests
uv run pytest tests/test_config_validation.py

# Run only idempotency tests
uv run pytest tests/test_idempotency.py

# Run only error handling tests
uv run pytest tests/test_error_handling.py
```

#### Skip Tests Requiring API Keys

```bash
# Skip tests that need real API access
uv run pytest -m "not requires_api_key"
```

#### Run Only Integration Tests

```bash
# Run only integration tests (requires API keys and network)
uv run pytest -m "integration"
```

#### Run with Coverage Report

```bash
# Generate code coverage report
uv run pytest --cov=src --cov-report=html --cov-report=term

# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Test Markers

Tests are marked with the following pytest markers:

- `@pytest.mark.integration` - Tests that require network access to fetch RSS feeds
- `@pytest.mark.requires_api_key` - Tests that require valid API keys (AssemblyAI, OpenAI, Gemini, Resend)
- `@pytest.mark.e2e` - End-to-end tests that run the full pipeline (slow, requires all API keys)

### Setting Up for Integration Tests

To run integration tests that require API keys:

1. Ensure your `.env` file has valid API keys:
   ```bash
   ASSEMBLYAI_API_KEY=<YOUR_ASSEMBLYAI_API_KEY>
   OPENAI_API_KEY=<YOUR_OPENAI_API_KEY>
   RESEND_API_KEY=<YOUR_RESEND_API_KEY>
   ```

2. Run integration tests:
   ```bash
   uv run pytest -m "integration"
   ```

### Continuous Integration

For CI environments, you can skip tests requiring API keys:

```bash
# Run only tests that don't need external services
uv run pytest -m "not integration and not requires_api_key and not e2e"
```

## Troubleshooting

### Service won't start

```bash
# Check service logs
sudo journalctl -u podcast-summary.service -n 50

# Verify paths and permissions
ls -la ~/podcast-summary
uv run main.py  # Run manually to see errors
```

### No emails received

- Check `system_email` in `config.yaml` matches your Resend verified domain
- Verify `RESEND_API_KEY` in `.env` is correct
- Check spam folder
- Look for errors in logs: `sudo journalctl -u podcast-summary.service`

### Transcription errors

- Verify `ASSEMBLYAI_API_KEY` in `.env`
- Check AssemblyAI account has credits
- Audio files must be accessible URLs or valid local files

### Database issues

```bash
# Check database integrity
sqlite3 data/podcasts.db "PRAGMA integrity_check;"

# Rebuild database (WARNING: deletes all data)
rm data/podcasts.db
uv run main.py  # Will recreate schema
```

## Cost Estimates

Typical costs for processing 5 podcasts with ~3 episodes/week each:

- **AssemblyAI**: $0.15/hour of audio
  - 15 episodes × 1 hour average = 15 hours/week
  - $2.25/week = ~$9/month
- **GPT-5-mini** (contextualization): ~$0.001 per episode
  - 15 episodes/week
  - Negligible cost (~$0.06/month)
- **Gemini 3 Pro** (summarization): ~$0.066 per episode
  - Typical episode: 15k input tokens, 1.5k output tokens, 1.5k thinking tokens
  - Rates: $2/million input tokens, $12/million output tokens
  - 15 episodes/week = ~$1/week = ~$4/month
- **Resend**: Free tier (100 emails/day) sufficient for personal use

**Total**: ~$13/month for moderate usage


## Credits

Built with:
- [Claude Code](https://www.claude.com/product/claude-code) - Code generation
- [AssemblyAI](https://www.assemblyai.com/) - Transcription
- [OpenAI](https://openai.com/) - AI Summarization
- [Google Gemini](https://ai.google.dev/) - AI Summarization
- [Resend](https://resend.com/) - Email Delivery
- [feedparser](https://github.com/kurtmckee/feedparser) - RSS parsing
