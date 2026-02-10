"""OpenAI GPT provider for LLM calls."""

import os
import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """OpenAI GPT provider for LLM calls."""

    def __init__(
        self,
        model: str,
        temperature: Optional[float] = None,
        reasoning_effort: Optional[str] = None
    ):
        """Initialize OpenAI provider.

        Args:
            model: Model to use for LLM calls (required)
                   Standard models: gpt-4o, gpt-4o-mini,4.1, etc.
                   Reasoning models: gpt-5.1, gpt-5, o3, o3-mini, etc
            temperature: Temperature for sampling (0.0-2.0, default 1.0)
                        Only for standard models. Reasoning models ignore this.
            reasoning_effort: Reasoning effort level for o-series models
                            Options: "low", "medium", "high"
                            Only applicable to reasoning models (o1, o3, etc.)
        """
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable must be set")

        self.model = model
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.client = OpenAI(api_key=self.api_key)

    def run(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Generate a completion for a fully constructed prompt.

        Args:
            message: Fully constructed prompt that includes transcript/user input
            system_prompt: Optional system instruction. If not provided, no system prompt is used.

        Returns:
            Generated completion text

        Raises:
            Exception: If API call fails
        """
        try:
            logger.info(f"Calling OpenAI API ({self.model})...")

            # Construct the input prompt - include system prompt only if provided
            if system_prompt:
                full_input = f"{system_prompt}\n\n{message}"
            else:
                full_input = message

            # Build API call parameters for Responses API
            api_params = {
                "model": self.model,
                "input": full_input
            }

            # Add temperature if specified (for standard models)
            if self.temperature is not None:
                api_params["temperature"] = self.temperature

            # Add reasoning effort if specified (for reasoning models)
            if self.reasoning_effort is not None:
                api_params["reasoning"] = {"effort": self.reasoning_effort}
            else:
                # For non-reasoning models, max_tokens is required/recommended
                # Default to 1000 if not specified
                api_params["max_tokens"] = 1000

            # Call OpenAI Responses API
            response = self.client.responses.create(**api_params)

            # Extract and log usage metadata if available
            if hasattr(response, 'usage'):
                usage = response.usage
                usage_info = {
                    'input_tokens': usage.input_tokens,
                    'output_tokens': usage.output_tokens,
                }
                
                # Add output token details if available
                if hasattr(usage, 'output_tokens_details') and usage.output_tokens_details:
                    if hasattr(usage.output_tokens_details, 'reasoning_tokens'):
                        usage_info['reasoning_tokens'] = usage.output_tokens_details.reasoning_tokens
                
                logger.info(f"OpenAI API usage: {usage_info}")
            else:
                logger.debug("Usage metadata not available in response")

            summary = response.output_text.strip()
            return summary

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
