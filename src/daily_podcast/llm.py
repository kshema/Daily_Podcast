from __future__ import annotations

from typing import Protocol

from openai import OpenAI


class LLMClient(Protocol):
    """Minimal interface the podcast agent needs from an LLM."""

    def generate_with_web_search(self, prompt: str) -> str:
        """Return generated text after optionally using current web search."""


class OpenAIResponsesLLM:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate_with_web_search(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
            input=prompt,
        )
        return response.output_text


def build_llm_client(provider: str, api_key: str, model: str) -> LLMClient:
    normalized = provider.strip().lower()
    if normalized == "openai":
        return OpenAIResponsesLLM(api_key=api_key, model=model)
    raise ValueError(f"Unsupported LLM provider: {provider}")
