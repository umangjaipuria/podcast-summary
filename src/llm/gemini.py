"""Google Gemini provider for LLM calls."""

import os
import logging
from typing import Optional
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Google Gemini provider for LLM calls."""

    def __init__(
        self,
        model: str,
        temperature: Optional[float] = None,
        thinking_level: Optional[str] = None,
        thinking_budget: Optional[int] = None
    ):
        """Initialize Gemini provider.

        Args:
            model: Model to use for LLMcalls (required)
                   Examples: gemini-2.5-flash, gemini-2.5-pro, gemini-3.0-pro, etc.
            temperature: Temperature for sampling (0.0-2.0)
                        Default is 1.0 (recommended for Gemini 3 models)
                        Lower values = more deterministic, higher = more creative
            thinking_level: Reasoning depth for Gemini 3 models
                          Options: "low", "high"
                          Low = faster, less reasoning; High = deeper reasoning
            thinking_budget: Token budget for reasoning (Gemini 2.5 models)
                           Integer value specifying max thinking tokens
                           Use -1 for automatic/dynamic thinking mode
        """
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable must be set")

        self.model_name = model
        self.temperature = temperature
        self.thinking_level = thinking_level
        self.thinking_budget = thinking_budget

        # Initialize Gemini client
        self.client = genai.Client(api_key=self.api_key)

    def run(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Run a Gemini call.

        Args:
            message: Fully constructed prompt to send to Gemini
            system_prompt: Optional system-level instruction that will be
                           prepended to the message before sending

        Returns:
            Generated completion text

        Raises:
            Exception: If API call fails
        """
        try:
            logger.info(f"Calling Gemini API ({self.model_name})...")

            # User message to send to Gemini
            contents = message

            # Build configuration
            config_params = {}
            if self.temperature is not None:
                config_params["temperature"] = self.temperature

            # Add thinking configuration (use whichever is set)
            if self.thinking_level is not None:
                # Convert string to ThinkingLevel enum
                thinking_level_enum = (
                    types.ThinkingLevel.HIGH if self.thinking_level.lower() == "high"
                    else types.ThinkingLevel.LOW
                )
                config_params["thinking_config"] = types.ThinkingConfig(
                    thinking_level=thinking_level_enum
                )
            elif self.thinking_budget is not None:
                config_params["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=self.thinking_budget
                )

            if system_prompt:
                config_params["system_instruction"] = types.Content(
                    role="system",
                    parts=[types.Part(text=system_prompt)]
                )

            # Build API call parameters
            api_params = {
                "model": self.model_name,
                "contents": contents
            }

            # Add config if any parameters are set
            if config_params:
                api_params["config"] = types.GenerateContentConfig(**config_params)

            # Generate content
            response = self.client.models.generate_content(**api_params)

            # Extract and log usage metadata if available
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                usage_info = {}
                
                if hasattr(usage, 'prompt_token_count'):
                    usage_info['input_tokens'] = usage.prompt_token_count
                if hasattr(usage, 'candidates_token_count'):
                    usage_info['output_tokens'] = usage.candidates_token_count
                if hasattr(usage, 'thoughts_token_count'):
                    usage_info['thinking_tokens'] = usage.thoughts_token_count
                
                if usage_info:
                    logger.info(f"Gemini API usage: {usage_info}")
            else:
                logger.debug("Usage metadata not available in response")

            summary = response.text.strip()
            return summary

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise
