"""Database operations for podcast monitoring system."""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)


def require_connection(func):
    """Decorator to ensure database connection exists before method execution."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.conn:
            raise RuntimeError("Database not connected")
        return func(self, *args, **kwargs)
    return wrapper


class Database:
    """SQLite database operations."""

    def __init__(self, db_path: str = "data/podcasts.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Establish database connection and enable foreign keys."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        logger.info(f"Connected to database: {self.db_path}")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def setup_and_sync(self, podcasts_config: List[Dict[str, Any]]):
        """Connect to database, initialize schema, and sync podcasts from config.

        This is a convenience method that combines the common initialization steps
        used by both main.py and run_pipeline.py.

        Args:
            podcasts_config: List of podcast configurations from podcasts.yaml
        """
        self.connect()
        self.initialize_schema()
        self.sync_podcasts(podcasts_config)

    @require_connection
    def initialize_schema(self):
        """Create all database tables if they don't exist."""
        cursor = self.conn.cursor()

        # podcasts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS podcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                active BOOLEAN NOT NULL DEFAULT 1,
                metadata TEXT,
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # episodes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                podcast_id INTEGER NOT NULL,
                episode_guid TEXT UNIQUE NOT NULL,
                title TEXT,
                description TEXT,
                link TEXT,
                audio_url TEXT,
                image_url TEXT,
                published_date TIMESTAMP,
                duration_minutes INTEGER,
                file_size_mb REAL,
                context TEXT,
                generated_summary TEXT,
                raw_rss TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (podcast_id) REFERENCES podcasts(id) ON DELETE RESTRICT
            )
        """)

        # processing_events table (append-only event log)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                event_data TEXT,
                additional_details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE RESTRICT
            )
        """)

        # Create indexes for performance on processing_events
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processing_events_episode_created
            ON processing_events(episode_id, created_at DESC)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processing_events_episode_status
            ON processing_events(episode_id, status)
        """)

        # Index for get_failed_episodes() - queries by status and created_at
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processing_events_status_created
            ON processing_events(status, created_at DESC)
        """)

        # email_log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                recipient_email TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE RESTRICT
            )
        """)

        # Create indexes for episodes table
        # Index for queries by podcast_id (foreign key lookups)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_podcast_id
            ON episodes(podcast_id)
        """)

        # Create indexes for email_log table
        # Compound index for email_already_sent() - queries by episode_id AND recipient_email
        # Also prevents duplicate email sends at DB level
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_email_log_episode_recipient
            ON email_log(episode_id, recipient_email)
        """)

        # Create indexes for podcasts table
        # Index for get_active_podcasts() - queries by active status
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_podcasts_active
            ON podcasts(active)
        """)

        self.conn.commit()
        logger.info("Database schema initialized")

    @require_connection
    def sync_podcasts(self, podcasts_config: List[Dict[str, Any]]):
        """Sync podcasts table from configuration.

        Args:
            podcasts_config: List of podcast configurations from podcasts.yaml
        """
        cursor = self.conn.cursor()
        config_slugs = {p['slug'] for p in podcasts_config}

        for podcast in podcasts_config:
            slug = podcast['slug']
            active = podcast['active']

            # Try to update first
            cursor.execute("""
                UPDATE podcasts
                SET active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE slug = ?
            """, (active, slug))

            # If no rows were updated, insert new podcast
            if cursor.rowcount == 0:
                cursor.execute("""
                    INSERT INTO podcasts (slug, active, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (slug, active))

        # Mark podcasts not in config as inactive
        cursor.execute("""
            UPDATE podcasts
            SET active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE slug NOT IN ({})
        """.format(','.join('?' * len(config_slugs))), list(config_slugs))

        self.conn.commit()
        logger.info(f"Synced {len(podcasts_config)} podcasts from config")

    @require_connection
    def get_podcast_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get podcast by slug."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM podcasts WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @require_connection
    def get_podcast_by_id(self, podcast_id: int) -> Optional[Dict[str, Any]]:
        """Get podcast by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM podcasts WHERE id = ?", (podcast_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @require_connection
    def update_podcast_last_checked(self, podcast_id: int):
        """Update last_checked timestamp for podcast."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE podcasts
            SET last_checked = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (podcast_id,))
        self.conn.commit()

    @require_connection
    def update_podcast_metadata(self, podcast_id: int, metadata: Dict[str, Any]):
        """Update podcast metadata (description, author, link from RSS).

        Args:
            podcast_id: Podcast ID
            metadata: Dictionary with description, author, link keys
        """
        import json
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE podcasts
            SET metadata = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (json.dumps(metadata), podcast_id))
        self.conn.commit()

    @require_connection
    def episode_exists(self, episode_guid: str) -> bool:
        """Check if episode exists by GUID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM episodes WHERE episode_guid = ?", (episode_guid,))
        return cursor.fetchone() is not None

    @require_connection
    def insert_episode(self, podcast_id: int, episode_data: Dict[str, Any]) -> int:
        """Insert new episode and return episode_id."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO episodes (
                podcast_id, episode_guid, title, description, link,
                audio_url, image_url, published_date, duration_minutes,
                file_size_mb, raw_rss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            podcast_id,
            episode_data['guid'],
            episode_data.get('title'),
            episode_data.get('description'),
            episode_data.get('link'),
            episode_data.get('audio_url'),
            episode_data.get('image_url'),
            episode_data.get('published_date'),
            episode_data.get('duration_minutes'),
            episode_data.get('file_size_mb'),
            episode_data.get('raw_rss')
        ))
        self.conn.commit()
        return cursor.lastrowid

    @require_connection
    def get_episode_by_id(self, episode_id: int) -> Optional[Dict[str, Any]]:
        """Get episode by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @require_connection
    def get_episode_by_guid(self, episode_guid: str) -> Optional[Dict[str, Any]]:
        """Get episode by GUID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM episodes WHERE episode_guid = ?", (episode_guid,))
        row = cursor.fetchone()
        return dict(row) if row else None

    @require_connection
    def update_episode_summary(self, episode_id: int, summary: str):
        """Update generated_summary for episode."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE episodes
            SET generated_summary = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (summary, episode_id))
        self.conn.commit()

    @require_connection
    def update_episode_file_size(self, episode_id: int, file_size_mb: float):
        """Update file_size_mb for episode after download."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE episodes
            SET file_size_mb = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (file_size_mb, episode_id))
        self.conn.commit()

    @require_connection
    def update_episode_context(self, episode_id: int, context: str):
        """Update context for episode."""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE episodes
            SET context = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (context, episode_id))
        self.conn.commit()

    @require_connection
    def add_processing_event(self, episode_id: int, status: str,
                            event_data: Optional[Dict[str, Any]] = None,
                            additional_details: Optional[str] = None):
        """Add a new processing event (append-only).

        Args:
            episode_id: Episode ID
            status: Event status (downloaded, transcribed, summarized, emailed, completed, failed)
            event_data: JSON-serializable dict with status-specific data
            additional_details: Additional text data (e.g., HTML email content)
        """
        import json

        cursor = self.conn.cursor()
        event_data_json = json.dumps(event_data) if event_data else None

        cursor.execute("""
            INSERT INTO processing_events (episode_id, status, event_data, additional_details)
            VALUES (?, ?, ?, ?)
        """, (episode_id, status, event_data_json, additional_details))
        self.conn.commit()

    @require_connection
    def get_latest_processing_event(self, episode_id: int) -> Optional[Dict[str, Any]]:
        """Get the most recent processing event for an episode."""
        import json

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM processing_events
            WHERE episode_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """, (episode_id,))
        row = cursor.fetchone()

        if not row:
            return None

        result = dict(row)
        # Parse JSON event_data if present
        if result.get('event_data'):
            try:
                result['event_data'] = json.loads(result['event_data'])
            except json.JSONDecodeError:
                result['event_data'] = None
        return result

    @require_connection
    def get_processing_events(self, episode_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all processing events for an episode, optionally filtered by status.

        Args:
            episode_id: Episode ID
            status: Optional status filter

        Returns:
            List of events ordered by created_at DESC, id DESC
        """
        import json

        cursor = self.conn.cursor()

        if status:
            cursor.execute("""
                SELECT * FROM processing_events
                WHERE episode_id = ? AND status = ?
                ORDER BY created_at DESC, id DESC
            """, (episode_id, status))
        else:
            cursor.execute("""
                SELECT * FROM processing_events
                WHERE episode_id = ?
                ORDER BY created_at DESC, id DESC
            """, (episode_id,))

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            # Parse JSON event_data if present
            if result.get('event_data'):
                try:
                    result['event_data'] = json.loads(result['event_data'])
                except json.JSONDecodeError:
                    result['event_data'] = None
            results.append(result)
        return results

    @require_connection
    def get_current_status(self, episode_id: int) -> Optional[str]:
        """Get the current processing status for an episode.

        Returns:
            Status string or None if no events exist
        """
        latest = self.get_latest_processing_event(episode_id)
        return latest['status'] if latest else None

    @require_connection
    def get_event_data(self, episode_id: int, status: str) -> Optional[Dict[str, Any]]:
        """Get event_data from the latest event of a specific status.

        Args:
            episode_id: Episode ID
            status: Status to filter by

        Returns:
            event_data dict or None if no matching event found
        """
        events = self.get_processing_events(episode_id, status)
        return events[0]['event_data'] if events else None

    @require_connection
    def email_already_sent(self, episode_id: int, recipient: str) -> bool:
        """Check if email already sent to recipient for episode."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 1 FROM email_log
            WHERE episode_id = ? AND recipient_email = ?
        """, (episode_id, recipient))
        return cursor.fetchone() is not None

    @require_connection
    def log_email_sent(self, episode_id: int, recipient: str):
        """Log successful email delivery."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO email_log (episode_id, recipient_email, sent_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (episode_id, recipient))
        self.conn.commit()

    @require_connection
    def get_failed_episodes(self, hours: Optional[int] = 24) -> List[Dict[str, Any]]:
        """Get failed episodes from the last N hours.

        Args:
            hours: Only return failures from the last N hours (default 24).
                   If None, returns all failed episodes.

        Returns:
            List of failed episode dictionaries with audio_path and error_message from event_data
        """
        import json

        cursor = self.conn.cursor()

        # Subquery to get latest event per episode
        if hours is None:
            cursor.execute("""
                SELECT
                    p.slug as podcast_slug,
                    e.title as episode_title,
                    pe.event_data,
                    pe.created_at as failed_at
                FROM processing_events pe
                JOIN episodes e ON pe.episode_id = e.id
                JOIN podcasts p ON e.podcast_id = p.id
                WHERE pe.status = 'failed'
                    AND pe.id IN (
                        SELECT id FROM processing_events pe2
                        WHERE pe2.episode_id = pe.episode_id
                        ORDER BY pe2.created_at DESC, pe2.id DESC
                        LIMIT 1
                    )
                ORDER BY pe.created_at DESC, pe.id DESC
            """)
        else:
            cursor.execute("""
                SELECT
                    p.slug as podcast_slug,
                    e.title as episode_title,
                    pe.event_data,
                    pe.created_at as failed_at
                FROM processing_events pe
                JOIN episodes e ON pe.episode_id = e.id
                JOIN podcasts p ON e.podcast_id = p.id
                WHERE pe.status = 'failed'
                    AND pe.created_at >= datetime('now', '-' || ? || ' hours')
                    AND pe.id IN (
                        SELECT id FROM processing_events pe2
                        WHERE pe2.episode_id = pe.episode_id
                        ORDER BY pe2.created_at DESC, pe2.id DESC
                        LIMIT 1
                    )
                ORDER BY pe.created_at DESC, pe.id DESC
            """, (hours,))

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            # Parse event_data to extract audio_path and error_message
            if result.get('event_data'):
                try:
                    event_data = json.loads(result['event_data'])
                    result['audio_path'] = event_data.get('audio_path')
                    result['error_message'] = event_data.get('error_message')
                except json.JSONDecodeError:
                    result['audio_path'] = None
                    result['error_message'] = None
            else:
                result['audio_path'] = None
                result['error_message'] = None
            # Remove event_data from final result
            del result['event_data']
            results.append(result)

        return results

    @require_connection
    def get_active_podcasts(self) -> List[Dict[str, Any]]:
        """Get all active podcasts."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM podcasts WHERE active = 1")
        return [dict(row) for row in cursor.fetchall()]
