"""Email service using Resend."""

import os
import logging
from typing import List, Optional
import resend
import markdown2

logger = logging.getLogger(__name__)


class Emailer:
    """Send emails via Resend."""

    def __init__(self, system_email: str, reply_to_email: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize emailer.

        Args:
            system_email: Email address to use as sender for all emails
            reply_to_email: Reply-to address for all outgoing emails
            api_key: Resend API key (defaults to RESEND_API_KEY env var)
        """
        self.api_key = api_key or os.getenv('RESEND_API_KEY')
        self.from_email = system_email
        self.reply_to_email = reply_to_email

        # Configure Resend
        resend.api_key = self.api_key

    def send_summary_email(self, podcast_name: str, episode_title: str,
                          episode_link: str, image_url: Optional[str],
                          summary: str, recipients: List[str],
                          podcast_image_url: Optional[str] = None,
                          podcast_link: Optional[str] = None,
                          duration_minutes: Optional[int] = None,
                          published_date: Optional[str] = None) -> tuple[bool, str]:
        """Send episode summary email using Batch API.

        Args:
            podcast_name: Name of podcast
            episode_title: Episode title
            episode_link: Link to original episode
            image_url: Episode artwork URL (optional)
            summary: Generated summary text
            recipients: List of recipient email addresses
            podcast_image_url: Podcast artwork URL for fallback (optional)
            podcast_link: Podcast's main website link for fallback (optional)
            duration_minutes: Episode duration in minutes (optional)
            published_date: Episode published date in ISO format (optional)

        Returns:
            Tuple of (success, html_content) where success is True if all emails sent successfully
        """
        subject = f"SUMMARY: {podcast_name}: {episode_title}"

        # Fall back to podcast image if episode image is missing
        final_image_url = image_url or podcast_image_url

        # Fall back to podcast link if episode link is missing
        final_episode_link = episode_link or podcast_link

        # Build HTML email body
        html_body = self._build_html_body(podcast_name, episode_title, final_episode_link,
                                          final_image_url, summary, duration_minutes,
                                          published_date, podcast_link)

        # Build plain text body (fallback)
        text_body = self._build_text_body(podcast_name, episode_title, final_episode_link,
                                          summary, duration_minutes, published_date, podcast_link)

        # Build batch params - one email per recipient
        batch_params = [
            {
                "from": f"Podcast Summary <{self.from_email}>",
                "to": [recipient],
                "subject": subject,
                "html": html_body,
                "text": text_body,
                **({"reply_to": [self.reply_to_email]} if self.reply_to_email else {})
            }
            for recipient in recipients
        ]

        try:
            logger.info(f"Sending batch email to {len(recipients)} recipient(s)...")
            response = resend.Batch.send(batch_params)

            # Response has 'data' array with email IDs and optional 'errors' array
            errors = response.get('errors', [])

            # Log success count
            if not errors:
                logger.info(f"Successfully sent emails to all {len(recipients)} recipient(s)")
            else:
                success_count = len(recipients) - len(errors)
                logger.info(f"Successfully sent emails to {success_count}/{len(recipients)} recipient(s)")

            # Log individual failures
            success = len(errors) == 0
            for error in errors:
                index = error.get('index', -1)
                message = error.get('message', 'Unknown error')
                recipient = recipients[index] if 0 <= index < len(recipients) else 'unknown'
                logger.error(f"Failed to send email to {recipient} (index {index}): {message}")

            return success, html_body

        except Exception as e:
            logger.error(f"Failed to send batch emails: {e}")
            return False, html_body

    def send_error_summary_email(self, failed_episodes: List[dict],
                                system_email: str) -> bool:
        """Send error summary email to system admin.

        Args:
            failed_episodes: List of failed episode dictionaries
            system_email: Admin email address

        Returns:
            True if email sent successfully, False otherwise
        """
        if not failed_episodes:
            logger.info("No failed episodes to report")
            return True

        subject = f"Podcast Monitor: {len(failed_episodes)} Failed Episodes"

        # Build error report
        html_body = self._build_error_html(failed_episodes)
        text_body = self._build_error_text(failed_episodes)

        try:
            logger.info(f"Sending error summary to {system_email}...")

            params = {
                "from": f"Podcast Summaries <{self.from_email}>",
                "to": [system_email],
                "subject": subject,
                "html": html_body,
                "text": text_body,
                **({"reply_to": [self.reply_to_email]} if self.reply_to_email else {})
            }

            response = resend.Emails.send(params)
            logger.info(f"Error summary sent: {response}")
            return True

        except Exception as e:
            logger.error(f"Failed to send error summary: {e}")
            return False

    def _format_duration(self, duration_minutes: Optional[int]) -> str:
        """Format duration in minutes to human-readable string."""
        if not duration_minutes:
            return ""

        if duration_minutes < 60:
            return f"{duration_minutes} min"

        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        if minutes == 0:
            return f"{hours}h"
        return f"{hours}h {minutes}m"

    def _format_published_date(self, published_date: str) -> str:
        """Format published date to human-readable string."""
        from datetime import datetime
        try:
            # Parse ISO format date
            dt = datetime.fromisoformat(published_date.replace('Z', '+00:00'))
            # Format as "Mon DD, YYYY" (3-letter month)
            # Check if time component exists (not midnight UTC)
            if dt.hour != 0 or dt.minute != 0:
                # Include time if present: "Dec 07, 2025 2:30 PM"
                return dt.strftime("%b %d, %Y %I:%M %p")
            else:
                # Date only: "Dec 07, 2025"
                return dt.strftime("%b %d, %Y")
        except (ValueError, AttributeError):
            # Return original if parsing fails
            return published_date

    def _build_html_body(self, podcast_name: str, episode_title: str, episode_link: str,
                        image_url: Optional[str], summary: str,
                        duration_minutes: Optional[int] = None,
                        published_date: Optional[str] = None,
                        podcast_link: Optional[str] = None) -> str:
        """Build HTML email body."""
        html = "<html><body style='font-family: Arial, sans-serif;'>"

        # Episode image if available
        if image_url:
            html += f"<img src='{image_url}' alt='Episode artwork' style='max-width: 250px; margin-bottom: 20px;'><br>"

        # Episode title
        html += f"<h2 style='margin-bottom: 8px;'>{episode_title}</h2>"

        # Podcast metadata section (small/diminutive)
        html += "<div style='font-size: 0.85em; color: #666; margin-bottom: 16px;'>"

        # Podcast link
        if podcast_link:
            html += f"<a href='{podcast_link}' style='color: #666; text-decoration: none;'>{podcast_name}</a>"
        else:
            html += f"{podcast_name}"

        # Published date
        if published_date:
            # Format the date nicely
            formatted_date = self._format_published_date(published_date)
            html += f" • {formatted_date}"

        html += "</div>"

        # Link to episode with duration
        duration_text = f" ({self._format_duration(duration_minutes)})" if duration_minutes else ""
        html += f"<p><a href='{episode_link}'>Listen to episode</a>{duration_text}</p>"

        # Summary
        html += "<hr>"
        # Convert markdown to HTML (with extras for better list handling)
        summary_html = markdown2.markdown(summary, extras=["cuddled-lists", "fenced-code-blocks", "tables"])
        html += f"<div style='margin-top: 20px;'>{summary_html}</div>"

        html += "</body></html>"
        return html

    def _build_text_body(self, podcast_name: str, episode_title: str, episode_link: str,
                        summary: str, duration_minutes: Optional[int] = None,
                        published_date: Optional[str] = None,
                        podcast_link: Optional[str] = None) -> str:
        """Build plain text email body."""
        text = f"{episode_title}\n\n"

        # Podcast metadata
        text += f"{podcast_name}"
        if published_date:
            formatted_date = self._format_published_date(published_date)
            text += f" • {formatted_date}"
        text += "\n"
        if podcast_link:
            text += f"{podcast_link}\n"
        text += "\n"

        # Episode link
        duration_text = f" ({self._format_duration(duration_minutes)})" if duration_minutes else ""
        text += f"Listen: {episode_link}{duration_text}\n\n"

        text += "=" * 60 + "\n\n"
        text += summary
        return text

    def _build_error_html(self, failed_episodes: List[dict]) -> str:
        """Build HTML error report."""
        html = "<html><body style='font-family: Arial, sans-serif;'>"
        html += f"<h2>Failed Episodes Report</h2>"
        html += f"<p>{len(failed_episodes)} episodes failed to process:</p>"
        html += "<table border='1' cellpadding='10' style='border-collapse: collapse;'>"
        html += "<tr><th>Podcast</th><th>Episode</th><th>Error</th><th>Failed At</th></tr>"

        for ep in failed_episodes:
            html += "<tr>"
            html += f"<td>{ep.get('podcast_slug', 'Unknown')}</td>"
            html += f"<td>{ep.get('episode_title', 'Unknown')}</td>"
            html += f"<td>{ep.get('error_message', 'No details')}</td>"
            html += f"<td>{ep.get('failed_at', 'Unknown')}</td>"
            html += "</tr>"

        html += "</table>"
        html += "</body></html>"
        return html

    def _build_error_text(self, failed_episodes: List[dict]) -> str:
        """Build plain text error report."""
        text = f"Failed Episodes Report\n"
        text += f"{len(failed_episodes)} episodes failed to process:\n\n"

        for ep in failed_episodes:
            text += f"Podcast: {ep.get('podcast_slug', 'Unknown')}\n"
            text += f"Episode: {ep.get('episode_title', 'Unknown')}\n"
            text += f"Error: {ep.get('error_message', 'No details')}\n"
            text += f"Failed At: {ep.get('failed_at', 'Unknown')}\n"
            text += "-" * 60 + "\n"

        return text
