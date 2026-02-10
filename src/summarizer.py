"""Summarization orchestrator."""

import logging
from pathlib import Path
from typing import Optional

# Import LLM provider - change this import to switch providers
from src.llm import gemini as llm_provider

logger = logging.getLogger(__name__)


class Summarizer:
    """Orchestrate LLM summarization."""

    def __init__(self, transcript_dir: str = "data/transcripts"):
        """Initialize summarizer.

        Args:
            transcript_dir: Directory containing transcripts
        """
        self.transcript_dir = Path(transcript_dir)

        # Gemini configuration
        # For Gemini 3.x models: use thinking_level="high"
        # For Gemini 2.5 models: change to thinking_budget=<int> (e.g., 1024)
        self.model = "gemini-3-pro-preview"
        self.temperature = 1.0
        self.thinking_level = "high"
        self.thinking_budget = None

    def summarize_transcript(self, transcript_path: str, prompt: str,
                            podcast_slug: str, episode_filename: str,
                            context: Optional[str] = None,
                            podcast_metadata: Optional[dict] = None,
                            system_prompt: Optional[str] = None) -> Optional[str]:
        """Generate summary from transcript.

        Args:
            transcript_path: Path to transcript file
            prompt: Custom prompt for summarization
            podcast_slug: Podcast slug (for organizing summaries)
            episode_filename: Base filename for summary (without extension)
            context: Optional context from episode metadata (participants, topics, etc)
            podcast_metadata: Optional podcast metadata (title, description, categories)
            system_prompt: Optional system-level instruction for the LLM

        Returns:
            Path to saved summary file or None if failed
        """
        try:
            # Read transcript
            logger.info(f"Reading transcript: {transcript_path}")
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript = f.read()

            if not transcript.strip():
                logger.error("Transcript is empty")
                return None

            # Generate summary using LLM provider
            logger.info(f"Generating summary with {self.model}...")

            # Build complete prompt with optional podcast context, episode context, and transcript
            prompt_parts = [prompt]

            # Add podcast context if available
            if podcast_metadata:
                podcast_context_parts = []
                if podcast_metadata.get('title'):
                    podcast_context_parts.append(f"Podcast: {podcast_metadata['title']}")
                if podcast_metadata.get('description'):
                    podcast_context_parts.append(f"Description: {podcast_metadata['description']}")
                if podcast_metadata.get('categories'):
                    categories_str = ', '.join(podcast_metadata['categories'])
                    podcast_context_parts.append(f"Categories: {categories_str}")

                if podcast_context_parts:
                    podcast_context = '\n'.join(podcast_context_parts)
                    prompt_parts.append(f"\n\nPodcast Context:\n{podcast_context}")

            # Add episode context if available
            if context:
                prompt_parts.append(f"\n\nEpisode Context (from metadata):\n{context}")

            prompt_parts.append(f"Full Transcript:\n\n{transcript}")

            complete_prompt = "\n\n".join(prompt_parts)

            # Create provider instance with configured parameters
            llm = llm_provider.GeminiProvider(
                model=self.model,
                temperature=self.temperature,
                thinking_level=self.thinking_level,
                thinking_budget=self.thinking_budget
            )

            summary = llm.run(complete_prompt, system_prompt=system_prompt)

            if not summary:
                logger.error("LLM returned empty summary")
                return None

            # Save summary
            podcast_dir = self.transcript_dir / podcast_slug
            podcast_dir.mkdir(parents=True, exist_ok=True)

            summary_filename = f"{episode_filename}.summary.txt"
            summary_path = podcast_dir / summary_filename

            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)

            logger.info(f"Saved summary to: {summary_path}")
            return str(summary_path)

        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            return None
