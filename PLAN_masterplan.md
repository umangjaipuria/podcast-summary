# Podcast Monitoring & Summarization System
## Architecture Specification

---

## Project Overview

A lightweight, automated system that monitors podcast RSS feeds, transcribes new episodes with speaker diarization, generates AI-powered summaries with relevant insights, and delivers results via email. Designed for personal use on a low-end VPS with daily execution via cron.

### Key Features
- Daily automated polling of podcast RSS feeds
- Transcription with speaker diarization
- AI-powered summarization and insight extraction
- Email delivery to multiple recipients per podcast
- YAML configuration for easy management

---

## System Architecture

The system follows a sequential pipeline architecture with five main components:

```
┌─────────────────────────────────────┐
│      Daily Cron Job (6 AM)          │
└────────────────┬────────────────────┘
                 │
    ┌────────────▼────────────┐
    │  Main Orchestrator       │
    └────────────┬────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼───┐  ┌─────▼─────┐  ┌───▼────┐
│  RSS  │  │Transcribe │  │  LLM   │
│Parser │─►│ +Diarize  │─►│Summary │
└───┬───┘  └───────────┘  └───┬────┘
    │                        │
    ▼                        ▼
┌──────────┐           ┌──────────┐
│  SQLite  │           │  Email   │
│ Database │           │ Service  │
└──────────┘           └──────────┘
```

---

## Component Recommendations

### 1. Database: SQLite ✅

**Recommendation:** SQLite (strongly recommended)

**Rationale:**
- Zero configuration, serverless architecture
- Minimal resource overhead (kilobytes of RAM)
- Single file database, easy backups
- No network latency
- Perfect for personal, single-user systems

**Schema:**
- `podcasts`: id, rss_url, name, last_checked
- `episodes`: id, podcast_id, episode_guid, title, published_date, audio_url
- `processed_episodes`: episode_id, transcription_path, summary_path, status, processed_date

**Note on podcast slug:** Currently stored only in `podcasts.yaml` configuration file, not in database. This keeps the database simple and avoids dual sources of truth. The slug is derived from config when needed for file operations. Database schema may be revisited if complexity increases.

### 2. Transcription + Diarization

**Decision:** AssemblyAI (Cloud API)

**Rationale:**
- Can handle multi-hour long audio files with diarization
- Cost effective at ~$0.65/hour
- Reliable speaker labeling for podcasts with multiple hosts/guests
- Official Python SDK available

**Future Considerations:**
- ElevenLabs - reportedly better accuracy (evaluate later)
- OpenAI GPT-4o transcribe+diarize - limited to 24MB MP3s (not suitable for long podcasts)

**Estimated monthly cost:** $6.50 for 10 hours of audio

### 3. LLM Summarization & Insights

**Recommendation:** Claude API, OpenAI API, or Gemini API

- Use any modern LLM API for summarization
- Allow custom prompts per podcast in config file
- Estimated cost: $2-5/month for typical usage

### 4. Email Service

**Decision:** Resend

**Rationale:**
- Already set up and configured
- Modern API with official SDK
- Reliable delivery

**Email Format:**
- Subject: `[Podcast Name] New Episode: {episode title}`
- Body: LLM-generated summary + link to original podcast episode (from RSS feed)

---

## Technology Stack

### Package Management
- **uv** - Fast Python package manager (instead of pip)

### Core Python Libraries (Official SDKs)

- **feedparser** - Parse podcast RSS feeds
- **requests** - Download audio files
- **sqlite3** - Database operations (built-in)
- **pyyaml** - Parse YAML configuration
- **assemblyai** - Official AssemblyAI SDK for transcription
- **anthropic** / **openai** / **google-genai** - Official LLM API SDKs
- **resend** - Official Resend SDK for email delivery

---

## Project Structure

```
podcast-monitor/
├── podcasts.yaml            # Podcast subscriptions
├── config.yaml              # Application settings
├── secrets.py               # API keys and credentials
├── main.py                  # Orchestrator
├── requirements.txt         # Python dependencies
├── src/
│   ├── __init__.py
│   ├── config_loader.py     # Load YAML configs
│   ├── rss_parser.py        # Fetch & parse RSS feeds
│   ├── database.py          # SQLite operations
│   ├── downloader.py        # Download audio files
│   ├── transcriber.py       # Transcription + diarization
│   ├── summarizer.py        # LLM-based summarization
│   └── emailer.py           # Send emails via Resend
├── data/
│   ├── podcasts.db          # SQLite database
│   ├── audio/
│   │   ├── downloaded/      # Freshly downloaded audio files
│   │   ├── processing/      # Currently being transcribed
│   │   └── archive/         # Completed audio files
│   └── transcripts/
│       └── {podcast-slug}/  # One folder per podcast
│           ├── yyyymmdd-episode-name.raw.txt      # Raw transcript with speaker labels
│           └── yyyymmdd-episode-name.summary.txt  # LLM summary
└── logs/
    └── app.log
```

---

## Configuration Files

### podcasts.yaml

Podcast subscriptions with metadata:

```yaml
podcasts:
  - name: "Tech Podcast"
    slug: "tech-podcast"      # REQUIRED: unique identifier
    rss_url: "https://example.com/feed.xml"
    emails:
      - "you@example.com"
      - "colleague@example.com"
    insights_prompt: "Focus on AI news and startup discussions"

  - name: "Business Podcast"
    slug: "biz-pod"            # REQUIRED: unique identifier
    rss_url: "https://business.com/feed.xml"
    emails:
      - "you@example.com"
    insights_prompt: "Extract key business insights and market trends"
```

**Important:** The `slug` field is required for each podcast. The system will error if it's missing.

### config.yaml

Application settings:

```yaml
settings:
  check_last_n_episodes: 3
  transcription_service: "assemblyai"
  llm_service: "claude"      # Options: "claude", "openai", "gemini"
  max_audio_length_minutes: 180
```

### secrets.py

API keys and credentials:

```python
# API Keys
ASSEMBLYAI_API_KEY = "your-assemblyai-key"
ANTHROPIC_API_KEY = "your-anthropic-key"  # or OPENAI_API_KEY, etc.
RESEND_API_KEY = "your-resend-key"

# Email Configuration
FROM_EMAIL = "podcasts@yourdomain.com"
```

---

## Execution Workflow

The system executes the following sequence daily:

1. Load configuration from `config.yaml` and `podcasts.yaml`
2. Validate that all podcasts have required `slug` field
3. For each podcast: fetch RSS feed and parse episodes
4. Check database for new episodes not yet processed
5. For each new episode:
   - Download audio file to `audio/downloaded/`
   - Move to `audio/processing/` during transcription
   - Send to AssemblyAI API with diarization enabled
   - Save transcript with speaker labels to `transcripts/{podcast-slug}/yyyymmdd-episode-name.txt`
   - Send transcript to LLM for summarization using podcast-specific prompt
   - Format email with summary + link to original podcast episode (from RSS)
   - Save summary to `transcripts/{podcast-slug}/yyyymmdd-episode-name.summary.txt`
   - Send email via Resend to configured recipients
   - Mark as processed in database
   - Move audio file to `audio/archive/`
6. Log results and exit

**File Naming Convention:**
- Format: `yyyymmdd-episode-name.ext`
- Date first for alphabetical sorting by publication date
- Episode name is sanitized (special chars removed, spaces replaced with hyphens)
- Reasonable length limit to avoid filesystem issues

---

## Resource Considerations

### Minimum VPS Requirements

- **RAM:** 1 GB (using cloud APIs)
- **Storage:** 10-20 GB (database, logs, temp files)
- **CPU:** Minimal (APIs do heavy lifting)

### Estimated Monthly Costs

Based on 5-10 hours of podcast audio per month:

- Transcription (AssemblyAI): ~$6.50
- LLM API (Claude/GPT): ~$2-5
- **Total: ~$10-15/month**

### Cron Setup

```bash
# Run daily at 6 AM
0 6 * * * cd /path/to/podcast-monitor && python3 main.py >> logs/cron.log 2>&1
```

---

## Additional Recommendations

- **Error handling:** Wrap all operations in try-except blocks with comprehensive logging
- **Rate limiting:** Add delays between API calls to avoid hitting limits
- **Retry logic:** Implement exponential backoff for network failures
- **Failure notifications:** Email yourself when the script encounters errors
- **Monitoring:** Log processing times and success rates
- **Cleanup & backups:** Separate script to handle archive cleanup and database backups

---

## Implementation Details

### File Naming & Sanitization

**Episode filename format:** `yyyymmdd-episode-name.ext`

Sanitization rules:
- Remove special characters (keep alphanumeric, hyphens, underscores)
- Replace spaces with hyphens
- Convert to lowercase
- Limit to 100 characters (excluding date prefix and extension)
- Strip leading/trailing hyphens

Example:
- Episode: "AI & Machine Learning: The Future!!"
- Published: 2024-03-15
- Result: `20240315-ai-machine-learning-the-future.txt`

### Configuration Validation

On startup, validate:
- All podcasts have required `slug` field (error and exit if missing)
- Slugs are unique across all podcasts
- RSS URLs are valid format
- Email addresses are valid format
- All required secrets are present in `secrets.py`

### Error Handling Strategy

- Podcast-level failures: Log error, skip podcast, continue with others
- Episode-level failures: Log error, skip episode, continue with others
- Critical failures (config, database): Error and exit
- API failures: Retry with exponential backoff (3 attempts)

---
