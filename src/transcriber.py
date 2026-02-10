"""Transcription service using AssemblyAI."""

import os
import logging
from pathlib import Path
from typing import Optional
import assemblyai as aai

logger = logging.getLogger(__name__)


class Transcriber:
    """Transcribe audio files with speaker diarization."""

    def __init__(self, api_key: str, transcript_dir: str = "data/transcripts"):
        """Initialize transcriber.

        Args:
            api_key: AssemblyAI API key
            transcript_dir: Directory to save transcripts
        """
        self.api_key = api_key
        self.transcript_dir = Path(transcript_dir)

        # Configure AssemblyAI
        aai.settings.api_key = api_key
        aai.settings.polling_interval = 10.0  # Poll every 10 seconds

        # Create transcript directory
        self.transcript_dir.mkdir(parents=True, exist_ok=True)

    def transcribe_audio(self, audio_path: str, podcast_slug: str,
                        episode_filename: str) -> Optional[str]:
        """Transcribe audio file with speaker diarization.

        Args:
            audio_path: Path to audio file
            podcast_slug: Podcast slug (for organizing transcripts)
            episode_filename: Base filename for transcript (without extension)

        Returns:
            Path to saved transcript file or None if failed
        """
        try:
            logger.info(f"Starting transcription for: {audio_path}")

            # Create podcast-specific directory
            podcast_dir = self.transcript_dir / podcast_slug
            podcast_dir.mkdir(parents=True, exist_ok=True)

            # Configure transcription with speaker diarization
            config = aai.TranscriptionConfig(
                speaker_labels=True,
                speakers_expected=None  # Auto-detect number of speakers
            )

            # Create transcriber
            transcriber = aai.Transcriber()

            # Transcribe audio (handles upload, submission, and polling internally)
            logger.info("Starting transcription (uploading and processing)...")
            transcript = transcriber.transcribe(audio_path, config=config)

            # Check for errors
            if transcript.status == aai.TranscriptStatus.error:
                logger.error(f"Transcription failed: {transcript.error}")
                return None

            # Format transcript with speaker labels
            formatted_transcript = self._format_transcript(transcript)

            # Save transcript
            transcript_filename = f"{episode_filename}.raw.txt"
            transcript_path = podcast_dir / transcript_filename

            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(formatted_transcript)

            logger.info(f"Saved transcript to: {transcript_path}")
            return str(transcript_path)

        except Exception as e:
            logger.error(f"Error during transcription: {e}")
            return None

    def _format_transcript(self, transcript) -> str:
        """Format transcript with speaker labels.

        Args:
            transcript: AssemblyAI transcript object

        Returns:
            Formatted transcript string
        """
        if not transcript.utterances:
            # Fallback to plain text if no speaker diarization
            return transcript.text

        formatted_lines = []
        for utterance in transcript.utterances:
            speaker = utterance.speaker
            text = utterance.text
            formatted_lines.append(f"Speaker {speaker}: {text}")

        return "\n\n".join(formatted_lines)

    @staticmethod
    def get_transcript_filename(episode_filename: str) -> str:
        """Get transcript filename from episode filename.

        Args:
            episode_filename: Episode filename (e.g., "20240315-episode-title.mp3")

        Returns:
            Transcript filename (e.g., "20240315-episode-title.raw.txt")
        """
        base = Path(episode_filename).stem
        return f"{base}.raw.txt"

    @staticmethod
    def get_summary_filename(episode_filename: str) -> str:
        """Get summary filename from episode filename.

        Args:
            episode_filename: Episode filename (e.g., "20240315-episode-title.mp3")

        Returns:
            Summary filename (e.g., "20240315-episode-title.summary.txt")
        """
        base = Path(episode_filename).stem
        return f"{base}.summary.txt"
