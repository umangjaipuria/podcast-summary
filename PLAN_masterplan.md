# Podcast Monitoring & Summarization System
## Architecture Specification & Implementation plan

---

## Project Overview

A lightweight, automated system that monitors podcast RSS feeds, transcribes new episodes with speaker diarization, generates AI-powered summaries with relevant insights, and delivers results via email. Designed for personal use on a low-end VPS with daily execution via systemd timer.

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
│   Daily Systemd Timer (6 AM)        │
└────────────────┬────────────────────┘
                 │
    ┌────────────▼────────────┐
    │  Main Orchestrator      │
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

### 1. Database
**Recommendation:** SQLite

**Rationale:**
- Zero configuration, serverless architecture
- Minimal resource overhead (kilobytes of RAM)
- Single file database, easy backups
- No network latency
- Perfect for personal, single-user systems

**Schema:**

**`podcasts` table** - Podcast registry synced from `podcasts.yaml` on each run
- Fields: `id`, `slug` (unique), `active` (boolean), `last_checked`, `created_at`, `updated_at`
- Purpose: Track which podcasts are monitored and when they were last checked
- Sync behavior: Insert new podcasts, update active flag from config, mark removed podcasts as inactive
- `last_checked` used with `podcast_check_interval_hours` config to throttle RSS fetching

**`episodes` table** - Episodes discovered from RSS feeds
- Fields: `id`, `podcast_id` (FK), `episode_guid` (unique), `title`, `description`, `link`, `audio_url`, `image_url`, `published_date`, `generated_summary`, `raw_rss`, `created_at`, `updated_at`
- Purpose: Store all episode metadata from RSS feed and generated summary
- `episode_guid`: Unique identifier from RSS used for deduplication
- `image_url`: Episode artwork/thumbnail from RSS feed (used in summary emails)
- `generated_summary`: LLM-generated summary text (populated after summarization step)
- `raw_rss`: Full XML blob of episode entry for debugging and audit trail
- `link`: Episode URL from RSS feed (included in summary emails)

**`processing_log` table** - Processing pipeline state tracking
- Fields: `id`, `episode_id` (FK), `status`, `transcript_path`, `summary_path`, `started_at`, `completed_at`, `error_message`, `created_at`, `updated_at`
- `status` values: 'downloaded', 'transcribed', 'summarized', 'emailed', 'completed', 'failed'
- Status represents last successful checkpoint
- `transcript_path`: File path to raw transcript (.raw.txt)
- `summary_path`: File path to generated summary (.summary.txt)
- `error_message`: Populated if status='failed', contains error details
- Purpose: Track episode progress through pipeline for monitoring and debugging
- Note: Summary text is stored in episodes.generated_summary column as well as a file in `data/transcripts/`

**`email_log` table** - Email delivery tracking
- Fields: id, episode_id (FK), recipient_email, sent_at, created_at, updated_at
- Purpose: One row per episode × recipient, tracks successful email deliveries
- Enables audit trail and potential resend functionality

### 2. Transcription + Diarization

**Decision:** AssemblyAI (Cloud API)

**Rationale:**
- Can handle multi-hour long audio files with diarization
- Cost effective at ~$0.27/hour
- Reliable speaker labeling for podcasts with multiple hosts/guests
- Official Python SDK available
- Asynchronous API (polling/webhook) - implementation will handle wait and retry logic internally

**Future Considerations:**
- ElevenLabs - reportedly better accuracy (evaluate later)
- OpenAI GPT-4o transcribe+diarize - limited to 24MB MP3s (will have to chunk for long podcasts)


### 3. LLM Summarization & Insights

**Recommendation:** Claude API, OpenAI API, or Gemini API

- Use any modern LLM API for summarization
- Allow custom prompts per podcast in config file

### 4. Email Service

**Decision:** Resend

**Rationale:**
- Already set up and configured
- Modern API with official SDK
- Reliable delivery

**Email Format:**
- Subject: `SUMMARY: {Podcast Name}: {episode title}`
- Body: Episode image + title as header, link to original podcast underneath, followed by LLM-generated summary 

---

## Technology Stack

### Package Management
- **uv** - faster / better than pip

### Core Python Libraries (Official SDKs)

- **feedparser** - Parse podcast RSS feeds
- **requests** - Download audio files
- **sqlite3** - Database operations (built-in)
- **pyyaml** - Parse YAML configuration
- **python-dotenv** - Load environment variables from .env file
- **assemblyai** - Official AssemblyAI SDK for transcription
- **openai** - OpenAI API SDK for GPT models
- **google-genai** - Google Gemini API SDK
- **resend** - Official Resend SDK for email delivery

---

## Project Structure

```
podcast-monitor/
├── .gitignore               # Git ignore patterns
├── .env                     # Environment variables (API keys, secrets)
├── dotenv.example           # Example environment file template (checked into git)
├── podcasts.yaml            # Podcast subscriptions (includes commented template)
├── config.yaml              # Application settings (includes commented template)
├── pyproject.toml           # Python dependencies (uv format)
├── main.py                  # Orchestrator
├── src/
│   ├── __init__.py
│   ├── config_loader.py     # Load and validate YAML configs and environment variables
│   ├── rss_parser.py        # Fetch & parse RSS feeds
│   ├── database.py          # SQLite operations
│   ├── downloader.py        # Download audio files
│   ├── transcriber.py       # Transcription + diarization (handles async polling)
│   ├── summarizer.py        # LLM orchestrator (uses provider-specific modules)
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── openai.py        # OpenAI GPT provider
│   │   └── gemini.py        # Google Gemini provider
│   └── emailer.py           # Send emails via Resend
├── deployment/
│   ├── podcast-monitor.service  # Systemd service unit file
│   └── podcast-monitor.timer    # Systemd timer unit file
├── scripts/
│   ├── cleanup_archives.py  # Remove old archived audio files
│   └── backup_database.py   # Backup SQLite database
└── data/
    ├── podcasts.db          # SQLite database
    ├── audio/
    │   ├── downloaded/      # Freshly downloaded audio files
    │   ├── processing/      # Currently being transcribed
    │   └── archive/         # Completed audio files
    └── transcripts/
        └── {podcast-slug}/  # One folder per podcast
            └── yyyymmdd-episode-name.raw.txt      # Raw transcript with speaker labels
            └── yyyymmdd-episode-name.summary.txt  # Generated summary

```

---

## Configuration Files

### podcasts.yaml

Podcast subscriptions with metadata. File includes a commented template at the top:

```yaml
# Template for adding new podcasts:
# - name: "Podcast Name"
#   slug: "podcast-slug"                          # REQUIRED: unique identifier (used for file paths)
#   rss_url: "https://example.com/feed.xml"       # REQUIRED: RSS feed URL
#   active: true                                  # REQUIRED: false = orchestrator skips this podcast
#   emails:                                       # NOT REQUIRED: no emails = orchestrator just skips processing this podcast
#     - "you@example.com"
#   insights_prompt: "Custom prompt for this podcast"  # OPTIONAL: uses default if not specified

podcasts:
  - name: "Tech Podcast"
    slug: "tech-podcast"
    rss_url: "https://example.com/feed.xml"
    active: true
    emails:
      - "you@example.com"
      - "colleague@example.com"
    insights_prompt: "Focus on AI news and startup discussions"

  - name: "Business Podcast"
    slug: "biz-pod"
    rss_url: "https://business.com/feed.xml"
    active: true
    emails:
      - "you@example.com"
    insights_prompt: "Extract key business insights and market trends"
```

**Required fields:** `slug`, `rss_url`, `active`
**Optional fields:** `emails`, `insights_prompt` (uses default from config.yaml if not specified)

### config.yaml

Application settings with inline documentation:

```yaml
settings:
  check_last_n_episodes: 3              # Number of recent episodes to check per feed
  podcast_check_interval_hours: 24      # Skip podcast if checked within this window
  max_audio_length_minutes: 240         # Skip episodes longer than this (checked from RSS <itunes:duration> tag)
                                        # If duration missing from RSS, process optimistically
                                        # Future: Could use mutagen library to check after download

  # Disk space management
  archive_retention_days: 15          # Delete archived audio files older than this
  max_audio_file_size_mb: 500           # Skip downloading files larger than this (MB)
  max_transcript_retention_days: 365    # Keep transcripts for 1 year

  # Error notifications
  system_email: "admin@example.com"     # Email address for system error notifications

# Default LLM prompt (used if podcast doesn't specify custom insights_prompt)
default_insights_prompt: |
  Provide a concise summary of this podcast episode including:
  - Main topics discussed (2-3 bullet points)
  - Key takeaways and insights
  - Notable quotes or moments
  - Actionable recommendations (if applicable)

  Keep the summary focused and under 300 words.
```

### .env

Environment variables for API keys and secrets:

```bash
# API Keys
ASSEMBLYAI_API_KEY=your-assemblyai-key
OPENAI_API_KEY=your-openai-key
GOOGLE_API_KEY=your-google-api-key
RESEND_API_KEY=your-resend-key

# Email Configuration
FROM_EMAIL=podcasts@yourdomain.com
```

---

## Execution Workflow

The system executes the following sequence daily:

1. **Load and validate all configurations** (via `config_loader.py`):
   - Load `config.yaml`, `podcasts.yaml`, and `.env`
   - Validate `podcasts.yaml` (required fields: slugs, URLs, emails, active flag; unique slugs; valid email formats)
   - Validate `config.yaml` (default prompt, settings, system_email)
   - Validate environment variables (API keys present and non-empty)
   - Exit with code 1 if any validation fails
2. **Sync podcasts table** from `podcasts.yaml`:
   - Insert new podcasts (new slugs)
   - Update existing podcasts: set active flag from config
   - Mark podcasts not in config as active=false (removed podcasts)
3. For each podcast in database where active=true:
   - **Check last_checked**: Skip if `(now - last_checked) < podcast_check_interval_hours`
   - Fetch RSS feed and parse last N episodes (from `check_last_n_episodes` config)
   - Update `last_checked` timestamp
4. For each episode from RSS:
   - Check if `episode_guid` exists in episodes table
   - Parse duration from RSS feed (`<itunes:duration>` tag, format: HH:MM:SS or seconds)
   - If duration > max_audio_length_minutes: Skip episode (log warning)
   - If duration missing from RSS: Process optimistically (don't skip)
   - If new: Insert into episodes table with full metadata (title, description, link, audio_url, image_url, raw_rss)
5. For each episode that needs processing:
   - **Include episodes where:** not in processing_log (new episodes only)
   - **Note:** Failed episodes (status='failed') are NOT retried - they remain marked as failed
   - Download audio file to `audio/downloaded/`
   - Update processing_log: status='downloaded' (or insert new row if not exists)
   - Move to `audio/processing/` during transcription
   - Send to AssemblyAI API with diarization enabled
   - Poll for transcription completion (handled internally by transcriber)
   - Save transcript with speaker labels to `transcripts/{podcast-slug}/yyyymmdd-episode-name.raw.txt`
   - Update processing_log: status='transcribed', transcript_path='{path}'
   - Send transcript to LLM for summarization using podcast-specific prompt (or default)
   - Save summary to `transcripts/{podcast-slug}/yyyymmdd-episode-name.summary.txt`
   - Update episodes table: set generated_summary column with generated text
   - Update processing_log: status='summarized', summary_path='{path}'
   - Format email with summary (from episodes.generated_summary column or .summary.txt file) + link to episode (from episodes.link field)
   - Send email via Resend to all recipients in podcast config
   - For each successful delivery: Insert row into email_log (episode_id, recipient_email, sent_at)
   - Update processing_log: status='emailed'
   - Update processing_log: status='completed', set completed_at timestamp
   - Move audio file to `audio/archive/`
   - **If any error occurs:** Log it, update processing_log with status='failed' and error_message, continue to next episode
6. **Clean up failed episodes:**
   - Query processing_log for episodes where status='failed'
   - For each failed episode: Delete associated audio files from downloaded/, processing/, and archive/ directories
   - Rationale: Prevents disk space accumulation from episodes that can't be processed (failures are not retried)
7. **Send error summary email:**
   - Query processing_log table for all failed episodes (where status='failed')
   - Join with episodes and podcasts tables to get full context
   - If any failures found, send single email to `system_email` listing all failed episodes
   - Include for each: podcast name, episode title, error message, failure timestamp
8. Log results and exit

**File Naming Convention:**
- Format: `yyyymmdd-episode-name.ext`
- Date prefix (`yyyymmdd`) is always the publication date
- Episode name is sanitized (special chars removed, spaces replaced with hyphens)
- Reasonable length limit to avoid filesystem issues
- Note: Episodes with dates in titles (e.g., "2024 in Review") will have format `20241215-2024-in-review.txt` - the first 8 digits are always the publication date

---

### Systemd Setup

**Service Unit File** (`deployment/podcast-monitor.service`):
```ini
[Unit]
Description=Podcast Monitor and Summarization Service
After=network-online.target

[Service]
Type=oneshot
User=vps-user
Group=vps-user
WorkingDirectory=/path/to/podcast-monitor
Environment="PATH=/path/to/podcast-monitor/.venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="HEALTHCHECKS_UUID=xyz"

# Timeout: Kill job if it runs longer than 6 hours
TimeoutStartSec=6h

# Healthchecks.io: Signal start
ExecStartPre=-/usr/bin/curl -fsS -m 10 --retry 5 -o /dev/null https://hc-ping.com/${HEALTHCHECKS_UUID}/start
# Run service via uv
ExecStart=/home/linuxbrew/.linuxbrew/bin/uv run main.py
# Healthchecks.io: Signal completion (success or failure)
ExecStopPost=/usr/bin/curl -fsS -m 10 --retry 5 -o /dev/null https://hc-ping.com/${HEALTHCHECKS_UUID}/$EXIT_STATUS

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=podcast-monitor
```

**Timer Unit File** (`deployment/podcast-monitor.timer`):
```ini
[Unit]
Description=Run Podcast Monitor daily at 6 AM

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Timeout Configuration:**
- `TimeoutStartSec=6h` ensures job doesn't hang indefinitely
- 6 hours allows for: multiple episodes × (download + 3hr max transcription + summarization + email)
- Systemd will kill the process if it exceeds this limit
- Can adjust based on actual workload (check `journalctl` logs for typical run times)

**Healthchecks.io Integration:**
- Pre-execution hook (`ExecStartPre`) pings healthchecks.io when job starts
- Post-execution hook (`ExecStopPost`) reports success/failure based on exit code
- Replace `YOUR-UUID` with actual healthchecks.io check UUID

**Logging:** All output (stdout/stderr) is captured by systemd journal. View logs with:
```bash
journalctl -u podcast-monitor.service -f  # Follow logs
journalctl -u podcast-monitor.service --since today  # Today's logs
```

---

## Additional Recommendations

- **Error handling:** Wrap all operations in try-except blocks with comprehensive logging (see Edge Case Handling section)
- **Rate limiting:** Add delays between API calls to avoid hitting limits
- **Monitoring:** Track processing times via `processing_log` table (started_at, completed_at fields)
- **Cleanup & backups:** Use included scripts (`scripts/cleanup_archives.py`, `scripts/backup_database.py`) - can be run via separate systemd timer

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

### Duration Checking Implementation

**Strategy:** Check RSS metadata to skip long episodes before download

**Implementation:**
- Parse duration from RSS `<itunes:duration>` tag during feed parsing (feedparser library)
- Duration format: `HH:MM:SS` (e.g., "3:45:22") or seconds (e.g., "13522")
- If duration > `max_audio_length_minutes`: Skip episode, log warning, don't add to processing queue
- If duration tag missing from RSS: Process episode optimistically (don't enforce limit)
- **Rationale:** Most podcasts include duration metadata, so this avoids downloading large files unnecessarily
- **Future enhancement:** After download, use `mutagen` library to read MP3 metadata and verify actual duration

**Why this approach:**
- No download needed for episodes with duration metadata (95%+ of cases)
- Fast - just RSS parsing with feedparser
- Fallback to optimistic processing when metadata missing (rare but graceful)
- Avoids complexity of post-download duration checking unless truly needed

### Configuration Validation

On startup, the system performs comprehensive validation via `config_loader.py`:

**podcasts.yaml validation:**
- Each podcast has required `slug` field (non-empty string)
- Each podcast has required `rss_url` field (valid URL format)
- Each podcast has required `active` field (boolean: true or false)
- Each podcast has required `emails` field (list with at least one email)
- All `slug` values are unique across all podcasts
- All email addresses are valid format (basic regex check)
- If validation fails, exit with error code 1

**config.yaml validation:**
- `default_insights_prompt` exists and is non-empty
- `system_email` exists and is valid email format
- Numeric values (retention days, file sizes) are positive integers
- If validation fails, exit with error code 1

**Environment variable validation:**
- `ASSEMBLYAI_API_KEY` is present and non-empty
- `RESEND_API_KEY` is present and non-empty
- `FROM_EMAIL` is present and valid email format
- LLM API key for the implemented provider (e.g., `OPENAI_API_KEY` or `GOOGLE_API_KEY` depending on code)
- If validation fails, exit with error code 1

**Exit codes:**
- `0`: Success
- `1`: Configuration or environment validation failed
- `2`: Runtime error (database, network, etc.)

### LLM Provider Abstraction

The system uses a provider abstraction layer to support multiple LLM services:

**Interface (all providers must implement):**
- Function name: `summarize(transcript, prompt)`
- Takes raw transcript text with speaker labels and custom prompt
- Returns generated summary text
- Raises exception if API call fails after retries

**Provider implementations:**
- `src/llm/openai.py` - Uses OpenAI GPT models (default: gpt-4o-mini)
- `src/llm/gemini.py` - Uses Google Gemini models (default: gemini-1.5-flash)

**How summarizer.py uses providers:**
1. Provider selection is **code-level** (hardcoded import in summarizer.py)
2. Import the chosen provider module
3. Call provider's summarize function with transcript and prompt
4. Handle retries and errors uniformly
5. **Note:** Switching providers requires code change, not config change

**Provider implementation details:**
- Each provider module creates API client using environment variable for API key
- Calls respective API with configured model
- Passes system prompt and transcript to model
- Returns generated summary text

### Error Handling Strategy

**Failure Levels:**
- **Podcast-level failures:** Log error, skip podcast, continue with others
- **Episode-level failures:** Log error, mark as 'failed' in processing_log with error_message, continue with others
- **Critical failures (config, database):** Error and exit with code 2
- **Configuration validation failures:** Exit with code 1
- **API failures:** Log error, mark episode as failed, continue with others (no retries)

**Error Notifications:**
- Errors are **not** sent to podcast subscribers (emails in `podcasts.yaml`)
- All errors are tracked in processing_log table with status='failed' and error_message
- At end of run, query database for all failed episodes and send **single error summary email** to `system_email` (from `config.yaml`)
- Error details include: podcast name, episode title, error message, failure timestamp
- Podcast subscribers only receive emails for successfully processed episodes
- Failed episodes are NOT retried - they remain in failed state permanently

### .gitignore

The `.gitignore` file prevents committing sensitive and generated files:

```gitignore
# Environment and secrets
.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python

# Virtual environments
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Data and generated files
data/
*.db
*.sqlite
*.sqlite3

# Logs (if any file-based logging is added later)
*.log
logs/

# macOS
.DS_Store

# Temporary files
*.tmp
*.temp
```

### Edge Case Handling

The system handles common edge cases gracefully:

**RSS Feed Issues:**
- **Temporarily unavailable (HTTP 5xx, timeout):** Log error, skip podcast for current run (will attempt RSS fetch again during next scheduled run)
- **Permanently moved (HTTP 301):** Log new URL (error, as this needs fixing), continue using old URL (admin should update config)
- **Not found (HTTP 404):** Log error, skip podcast, continue (requires manual intervention)
- **Malformed XML:** Log error with details, skip podcast, continue

**Episode Audio Issues:**
- **Missing audio enclosure in RSS:** Skip episode, log error
- **Audio URL returns 404:** Mark episode as failed (likely expired/removed)
- **Audio URL returns 5xx:** Mark episode as failed (likely server error)
- **File size exceeds `max_audio_file_size_mb`:** Skip episode, log error
- **Download interrupted/corrupted:** Mark episode as failed

**Transcription Issues:**
- **AssemblyAI API unavailable:** Mark failed, log error
- **Transcription job stuck/timeout:** Wait up to 3 hours, then mark as failed
- **Transcription returns error:** Mark as failed, log error message from API

**LLM Summarization Issues:**
- **API unavailable/rate limited:** Mark as failed, log error
- **Transcript too long for context window:** Mark as failed, log error
- **Invalid response:** Mark as failed, log error

**Email Delivery Issues:**
- **Resend API unavailable:** Log error, mark episode as 'failed'
- **Invalid email address:** Log error, skip that recipient, continue with others
- **Note:** Failed episodes remain in database permanently and are never retried

**Database Integrity:**
- Database integrity checks on startup (foreign key constraints, orphaned records)

---

## Testing Strategy

The system uses a focused set of integration and end-to-end tests to verify core functionality. Tests use real external services (RSS feeds, AssemblyAI, LLM APIs, Resend) to ensure the full pipeline works correctly.

### Core Integration Tests (6 tests)

**1. Config Validation**
- Test missing required field in podcasts.yaml → exit code 1
- Test invalid email format → exit code 1
- Test missing API key → exit code 1
- Test valid config → passes validation

**2. Download Episode**
- Download new episode from real RSS feed
- Verify episodes table populated with: title, description, link, image_url, raw_rss
- Verify processing_log has status='downloaded'
- Verify audio file exists in archive directory

**3. Transcribe Episode**
- Transcribe one real audio file using AssemblyAI
- Verify .raw.txt file created with correct naming format
- Verify processing_log updated: status='transcribed', transcript_path set correctly

**4. Summarize Episode**
- Summarize one real transcript using LLM
- Test with custom podcast prompt
- Test with default prompt
- Verify episodes.generated_summary column populated with summary text
- Verify processing_log updated: status='summarized'

**5. Email Summary**
- Send one real email via Resend API
- Verify email_log has entry for each recipient
- Verify processing_log updated: status='emailed'

**6. Idempotency & Duplicates**
- Run download twice → episode not re-inserted (GUID deduplication)
- Episode already in processing_log → skip processing
- Email already sent (in email_log) → don't re-send

### End-to-End Test (1 test)

**7. Full Pipeline**
- Add test podcast to config
- Run full orchestrator
- Verify complete flow: RSS fetch → download → transcribe → summarize → email → DB updates
- Run orchestrator again → verify no duplicate processing

### Error Handling Tests (2 tests)

**8. Episode-Level Failure Handling**
- Force error mid-pipeline (e.g., provide invalid audio file)
- Verify processing_log: status='failed', error_message populated
- Verify error summary email sent to system_email
- Verify next episode still processes (failure isolation)
- Verify failed episode is NOT retried on subsequent runs

**9. Podcast Check Interval Throttling**
- Process podcast (last_checked timestamp set)
- Run again within interval → podcast skipped
- Run after interval expires → podcast processed

**Total: 9 focused tests**

These tests cover the critical paths while avoiding unnecessary complexity around API failures, file system operations, and other implementation details that are either simple or externally managed.

---

