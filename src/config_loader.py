"""Configuration loader and validator."""

import os
import re
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Configuration validation error."""
    pass


class ConfigLoader:
    """Load and validate all configuration files."""

    def __init__(self,
                 podcasts_yaml: str = "podcasts.yaml",
                 config_yaml: str = "config.yaml",
                 env_file: str = ".env"):
        """Initialize config loader."""
        self.podcasts_yaml = podcasts_yaml
        self.config_yaml = config_yaml
        self.env_file = env_file

        self.podcasts_config: List[Dict[str, Any]] = []
        self.app_config: Dict[str, Any] = {}
        self.env_vars: Dict[str, str] = {}

    def load_all(self) -> bool:
        """Load and validate all configurations.

        Returns:
            True if all configs valid, False otherwise
        """
        try:
            self._load_env()
            self._load_podcasts_config()
            self._load_app_config()
            self._validate_all()
            logger.info("All configurations loaded and validated successfully")
            return True
        except ConfigError as e:
            logger.error(f"Configuration validation failed: {e}")
            return False

    def _load_env(self):
        """Load environment variables from .env file."""
        if Path(self.env_file).exists():
            load_dotenv(self.env_file)
            logger.info(f"Loaded environment from {self.env_file}")
        else:
            logger.error(f"Environment file {self.env_file} not found")

        # Collect required env vars
        self.env_vars = {
            'ASSEMBLYAI_API_KEY': os.getenv('ASSEMBLYAI_API_KEY', ''),
            'RESEND_API_KEY': os.getenv('RESEND_API_KEY', ''),
            'OPENAI_API_KEY': os.getenv('OPENAI_API_KEY', ''),
            'GEMINI_API_KEY': os.getenv('GEMINI_API_KEY', ''),
        }

    def _load_podcasts_config(self):
        """Load podcasts.yaml configuration."""
        try:
            with open(self.podcasts_yaml, 'r') as f:
                data = yaml.safe_load(f)
                # Handle empty YAML files (yaml.safe_load returns None)
                if data is None:
                    data = {}
                self.podcasts_config = data.get('podcasts', [])
            logger.info(f"Loaded {len(self.podcasts_config)} podcasts from {self.podcasts_yaml}")
        except FileNotFoundError:
            raise ConfigError(f"Podcasts config file not found: {self.podcasts_yaml}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {self.podcasts_yaml}: {e}")

    def _load_app_config(self):
        """Load config.yaml configuration."""
        try:
            with open(self.config_yaml, 'r') as f:
                self.app_config = yaml.safe_load(f)
                # Handle empty YAML files (yaml.safe_load returns None)
                if self.app_config is None:
                    self.app_config = {}
            logger.info(f"Loaded application config from {self.config_yaml}")
        except FileNotFoundError:
            raise ConfigError(f"Application config file not found: {self.config_yaml}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {self.config_yaml}: {e}")

    def _validate_all(self):
        """Validate all configurations."""
        self._validate_podcasts()
        self._validate_app_config()
        self._validate_env_vars()

    def _validate_podcasts(self):
        """Validate podcasts.yaml configuration."""
        if not self.podcasts_config:
            raise ConfigError("No podcasts defined in podcasts.yaml")

        slugs = set()
        for i, podcast in enumerate(self.podcasts_config):
            # Required fields
            if 'name' not in podcast or not podcast['name']:
                raise ConfigError(f"Podcast {i}: 'name' field is required and must be non-empty")

            if 'slug' not in podcast or not podcast['slug']:
                raise ConfigError(f"Podcast {i}: 'slug' field is required and must be non-empty")

            if 'rss_url' not in podcast or not podcast['rss_url']:
                raise ConfigError(f"Podcast {i}: 'rss_url' field is required and must be non-empty")

            if 'active' not in podcast:
                raise ConfigError(f"Podcast {i}: 'active' field is required")

            if not isinstance(podcast['active'], bool):
                raise ConfigError(f"Podcast {i}: 'active' must be a boolean (true/false)")

            # Validate slug uniqueness
            slug = podcast['slug']
            if slug in slugs:
                raise ConfigError(f"Duplicate slug found: '{slug}'")
            slugs.add(slug)

            # Validate URL format (basic check)
            rss_url = podcast['rss_url']
            if not rss_url.startswith(('http://', 'https://')):
                raise ConfigError(f"Podcast '{slug}': Invalid RSS URL format")

            # Validate emails if present
            if 'emails' in podcast:
                emails = podcast['emails']
                if not isinstance(emails, list):
                    raise ConfigError(f"Podcast '{slug}': 'emails' must be a list")

                if not emails:
                    logger.warning(f"Podcast '{slug}': No emails configured - episodes will not be sent")

                for email in emails:
                    if not self._is_valid_email(email):
                        raise ConfigError(f"Podcast '{slug}': Invalid email format: {email}")

        logger.info(f"Validated {len(self.podcasts_config)} podcasts")

    def _validate_app_config(self):
        """Validate config.yaml configuration."""
        # Check required sections
        if 'settings' not in self.app_config:
            raise ConfigError("Missing 'settings' section in config.yaml")

        if 'summary_default_prompt' not in self.app_config:
            raise ConfigError("Missing 'summary_default_prompt' in config.yaml")

        if 'summary_system_prompt' not in self.app_config:
            raise ConfigError("Missing 'summary_system_prompt' in config.yaml")

        settings = self.app_config['settings']

        # Validate default prompt
        default_prompt = self.app_config['summary_default_prompt']
        if not default_prompt or not default_prompt.strip():
            raise ConfigError("'summary_default_prompt' cannot be empty")

        # Validate system prompt
        system_prompt = self.app_config['summary_system_prompt']
        if not system_prompt or not system_prompt.strip():
            raise ConfigError("'summary_system_prompt' cannot be empty")

        # Validate system_email
        system_email = settings.get('system_email')
        if not system_email:
            raise ConfigError("'system_email' is required in settings")

        if not self._is_valid_email(system_email):
            raise ConfigError(f"Invalid system_email format: {system_email}")

        # Validate numeric settings
        numeric_settings = [
            'check_last_n_episodes',
            'max_audio_length_minutes',
            'archive_retention_days',
            'max_audio_file_size_mb',
            'max_transcript_retention_days'
        ]

        for setting in numeric_settings:
            if setting in settings:
                value = settings[setting]
                if not isinstance(value, int) or value <= 0:
                    raise ConfigError(f"Setting '{setting}' must be a positive integer")

        logger.info("Validated application config")

    def _validate_env_vars(self):
        """Validate required environment variables."""
        # Required for all configurations
        required_vars = ['ASSEMBLYAI_API_KEY', 'RESEND_API_KEY']

        # At least one LLM API key required
        llm_keys = ['OPENAI_API_KEY', 'GEMINI_API_KEY']
        has_llm_key = any(self.env_vars.get(key) for key in llm_keys)

        missing = []
        for var in required_vars:
            if not self.env_vars.get(var):
                missing.append(var)

        if not has_llm_key:
            missing.append("OPENAI_API_KEY or GEMINI_API_KEY")

        if missing:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")

        logger.info("Validated environment variables")

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Basic email format validation."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def get_podcasts(self) -> List[Dict[str, Any]]:
        """Get podcasts configuration."""
        return self.podcasts_config

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a specific setting value."""
        return self.app_config.get('settings', {}).get(key, default)

    def get_default_prompt(self) -> str:
        """Get default summary prompt."""
        return self.app_config.get('summary_default_prompt', '')

    def get_system_prompt(self) -> str:
        """Get summary system prompt."""
        return self.app_config.get('summary_system_prompt', '')

    def get_contextualize_prompt(self) -> str:
        """Get default contextualize prompt."""
        return self.app_config.get('default_contextualize_prompt', '')
