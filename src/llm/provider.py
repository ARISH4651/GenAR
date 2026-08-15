"""
src/llm/provider.py

LLMProvider abstraction + GeminiProvider implementation.

Design:
  - LLMProvider is an abstract base class with a single .generate() method.
  - GeminiProvider implements it using the google-generativeai SDK.
  - Any other provider (OpenAI, Anthropic, etc.) can be added without
    changing the rest of the pipeline.

Why an abstraction here?
  The LLM is the only replaceable component in the pipeline. Everything
  else (validation, analysis, evidence, prompts) is provider-agnostic.
  The abstraction documents that boundary explicitly.

API key is read from the GEMINI_API_KEY environment variable.
The application fails fast with a clear error if the key is missing.
"""

from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Default generation parameters
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_TEMPERATURE = 0.3   # Low for regulatory text — consistent, factual output
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5.0   # seconds, doubles on each retry


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, response_schema: Any | None = None) -> str | BaseModel:
        """
        Generate text given a system prompt and a user prompt.

        Args:
            system_prompt: Global behaviour instructions.
            user_prompt:   Section-specific context + evidence + instructions.

        Returns:
            Generated text string.

        Raises:
            LLMError: If generation fails after all retries.
        """


class LLMError(RuntimeError):
    """Raised when the LLM provider fails to generate a response."""


class GeminiProvider(LLMProvider):
    """
    Gemini implementation of LLMProvider.

    Reads GEMINI_API_KEY from the environment.
    Uses gemini-3.5-flash by default.
    Implements simple exponential-backoff retry for transient errors.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise LLMError(
                "GEMINI_API_KEY is not set. "
                "Copy .env.example to .env and add your API key, "
                "or set the environment variable directly."
            )

        self.model_name = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        self.temperature = temperature
        self.max_retries = max_retries

        self._client = self._build_client()
        logger.info("GeminiProvider ready (model=%s, temperature=%.1f)", self.model_name, self.temperature)

    def _build_client(self):
        """Initialise the Gemini generative model using google-genai."""
        try:
            from google import genai
        except ImportError:
            raise LLMError(
                "google-genai is not installed. "
                "Run: pip install google-genai"
            )

        return genai.Client(api_key=self.api_key)

    def generate(self, system_prompt: str, user_prompt: str, response_schema: Any | None = None) -> str | BaseModel:
        """
        Generate text or structured JSON using Gemini with retry on transient failures.
        """
        from google import genai
        from google.genai.errors import APIError

        delay = DEFAULT_RETRY_DELAY
        last_error = None

        config_args = {
            "temperature": self.temperature,
            "system_instruction": system_prompt,
            "automatic_function_calling": genai.types.AutomaticFunctionCallingConfig(disable=True)
        }

        if response_schema:
            config_args["response_mime_type"] = "application/json"
            config_args["response_schema"] = response_schema

        config = genai.types.GenerateContentConfig(**config_args)

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug("Gemini call attempt %d/%d", attempt, self.max_retries)
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=config,
                )
                
                if response_schema:
                    if not response.parsed:
                        raise LLMError("Gemini failed to return valid JSON matching the schema.")
                    return response.parsed
                
                text = response.text
                if not text or not text.strip():
                    raise LLMError("Gemini returned an empty response.")
                logger.debug("Gemini response: %d chars", len(text))
                return text

            except APIError as e:
                # E.g. resource exhausted, service unavailable, etc.
                last_error = e
                
                # Fast fail on quota exhaustion (429)
                if e.code == 429:
                    logger.error("Gemini quota exhausted (429). Failing fast to avoid unnecessary retries.")
                    raise LLMError(f"Gemini API Quota Exhausted: {e}") from e

                if attempt < self.max_retries:
                    logger.warning(
                        "Gemini transient error (attempt %d/%d): %s. Retrying in %.0fs ...",
                        attempt, self.max_retries, e, delay
                    )
                    time.sleep(delay)
                    delay *= 2  # exponential backoff
                else:
                    logger.error("Gemini failed after %d attempts.", self.max_retries)

            except Exception as e:
                raise LLMError(f"Gemini generation error: {e}") from e

        raise LLMError(
            f"Gemini failed after {self.max_retries} retries. Last error: {last_error}"
        )


class StubProvider(LLMProvider):
    """
    Stub provider for testing without an API key.

    Returns a placeholder message for every section.
    Use with --skip-llm flag in the CLI.
    """

    def generate(self, system_prompt: str, user_prompt: str, response_schema: Any | None = None) -> str | BaseModel:
        if response_schema:
            return response_schema(
                narrative_summary="[STUB] Narrative summary generated here.",
                case_analysis="[STUB] Case analysis generated here.",
                reaction_analysis="[STUB] Reaction analysis generated here.",
                trends="[STUB] Trends generated here."
            )
            
        section = "Unknown Section"
        for line in user_prompt.splitlines():
            if line.startswith("SECTION:"):
                section = line.replace("SECTION:", "").strip()
                break
        return (
            f"[STUB — LLM SKIPPED]\n\n"
            f"This section ({section}) was not generated because --skip-llm was specified. "
            f"Run without --skip-llm and with a valid GEMINI_API_KEY to generate real content."
        )
