"""Contextualization for podcast episodes using metadata."""

import logging
from typing import Optional
from datetime import datetime

# Use OpenAI GPT-5-mini for fast, cheap contextualization
from src.llm import openai as llm_provider

logger = logging.getLogger(__name__)


class Contextualizer:
    """Extract context from episode metadata before transcription."""

    def __init__(self):
        """Initialize contextualizer.

        Uses OpenAI GPT-5-mini for fast, cheap context extraction with low reasoning effort.
        """
        # Use fast, cheap model for metadata extraction
        self.model = "gpt-5-mini"
        self.reasoning_effort = "medium"

    def contextualize_episode(self,
                              podcast_name: str,
                              podcast_author: Optional[str],
                              podcast_description: Optional[str],
                              episode_title: str,
                              published_date: Optional[str],
                              episode_description: Optional[str],
                              episode_link: Optional[str],
                              prompt: str) -> Optional[str]:
        """Generate context from episode metadata.

        Args:
            podcast_name: Name of the podcast
            podcast_author: Podcast author/creator
            podcast_description: Podcast description/about
            episode_title: Title of the episode
            published_date: Publication date (string or datetime)
            episode_description: Episode description from RSS (optional)
            episode_link: Episode URL
            prompt: Contextualization prompt

        Returns:
            Context string or None if failed
        """
        try:
            # Build metadata summary (podcast info first, then episode info)
            metadata_parts = [
                f"Podcast: {podcast_name}"
            ]

            if podcast_author:
                metadata_parts.append(f"Author: {podcast_author}")

            if podcast_description:
                metadata_parts.append(f"Podcast Description: {podcast_description}")

            metadata_parts.append(f"Episode: {episode_title}")

            if published_date:
                # Handle both string and datetime objects
                if isinstance(published_date, datetime):
                    date_str = published_date.strftime("%Y-%m-%d")
                else:
                    date_str = str(published_date)
                metadata_parts.append(f"Published: {date_str}")

            if episode_description:
                metadata_parts.append(f"Episode Description: {episode_description}")
            else:
                metadata_parts.append("Episode Description: (not provided)")

            if episode_link:
                metadata_parts.append(f"Episode Link: {episode_link}")

            metadata = "\n".join(metadata_parts)

            logger.info(f"Generating context for episode: {episode_title}")

            # Create provider instance
            provider = llm_provider.OpenAIProvider(
                model=self.model,
                reasoning_effort=self.reasoning_effort
            )

            # Generate context
            message = f"{prompt}\n\nPodcast & Episode Information:\n\n{metadata}"
            context = provider.run(message)

            if not context or not context.strip():
                logger.error("LLM returned empty context")
                return None

            logger.info(f"Generated context ({len(context)} chars)")
            return context.strip()

        except Exception as e:
            logger.error(f"Error during contextualization: {e}")
            return None
