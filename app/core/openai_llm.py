"""Custom LLM wrapper for ChatGPT 4o mini via OpenAI."""
from __future__ import annotations

import os
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from openai import AsyncOpenAI


class OpenAILlm(BaseLlm):
    """Minimal BaseLlm implementation that proxies to OpenAI Chat Completions."""

    api_key: str | None = None

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        """Generate a single response using OpenAI Chat Completions API."""
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Please configure it in the environment."
            )

        client = AsyncOpenAI(api_key=api_key)

        messages = self._convert_contents_to_messages(llm_request)

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=llm_request.config.temperature or 0.7,
        )

        content_text = ""
        if response.choices:
            content_text = response.choices[0].message.content or ""

        llm_response = LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=content_text)],
            ),
            model_version=self.model,
        )
        yield llm_response

    def _convert_contents_to_messages(self, llm_request) -> list[dict]:
        """Convert ADK contents + system instruction into OpenAI messages."""
        messages: list[dict] = []

        system_instruction = llm_request.config.system_instruction
        if system_instruction:
            if isinstance(system_instruction, list):
                system_text = "\n\n".join(system_instruction)
            else:
                system_text = str(system_instruction)
            messages.append({"role": "system", "content": system_text})

        for content in llm_request.contents:
            text_parts = []
            for part in content.parts or []:
                if part.text:
                    text_parts.append(part.text)
            if text_parts:
                messages.append(
                    {
                        "role": content.role or "user",
                        "content": "\n".join(text_parts),
                    }
                )

        if not messages:
            messages.append(
                {
                    "role": "user",
                    "content": "Respond to the system instruction.",
                }
            )

        return messages

