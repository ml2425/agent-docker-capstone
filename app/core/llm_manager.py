"""LLM configuration manager with ChatGPT default and Gemini option."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

from google.adk.models.google_llm import Gemini

from app.core.openai_llm import OpenAILlm


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMConfig:
    """Configuration metadata for selectable LLMs."""

    identifier: str
    label: str
    provider: str  # "openai" | "gemini"
    model_name: str
    description: str = ""
    default: bool = False


class LLMManager:
    """Central registry for supported LLMs with graceful fallback."""

    def __init__(self) -> None:
        self._configs: Dict[str, LLMConfig] = {}
        self._model_cache: Dict[str, object] = {}
        self._default_id: Optional[str] = None

        self._register_default_configs()

    def _register_default_configs(self) -> None:
        self.register_config(
            LLMConfig(
                identifier="chatgpt_4o_mini",
                label="ChatGPT 4o mini (default)",
                provider="openai",
                model_name="gpt-4o-mini",
                description="OpenAI GPT-4o mini for fast, reliable HITL review.",
                default=True,
            )
        )
        self.register_config(
            LLMConfig(
                identifier="gemini_2_5_flash_lite",
                label="Gemini 2.5 Flash Lite",
                provider="gemini",
                model_name="gemini-2.5-flash-lite",
                description="Google Gemini 2.5 Flash Lite for low-latency operations.",
            )
        )

    def register_config(self, config: LLMConfig) -> None:
        self._configs[config.identifier] = config
        if config.default or self._default_id is None:
            self._default_id = config.identifier

    @property
    def default_id(self) -> str:
        if not self._default_id:
            raise ValueError("No default LLM configured.")
        return self._default_id

    def list_configs(self) -> List[LLMConfig]:
        return list(self._configs.values())

    def get_config(self, model_id: Optional[str]) -> LLMConfig:
        if model_id and model_id in self._configs:
            return self._configs[model_id]
        return self._configs[self.default_id]

    def get_label(self, model_id: Optional[str]) -> str:
        return self.get_config(model_id).label

    def get_choices(self) -> List[str]:
        return [config.identifier for config in self.list_configs()]

    def get_model(self, model_id: Optional[str]) -> object:
        """Return (and cache) the LLM instance for the given model id."""
        config = self.get_config(model_id)
        if config.identifier in self._model_cache:
            return self._model_cache[config.identifier]

        model_instance = self._create_model(config)
        self._model_cache[config.identifier] = model_instance
        return model_instance

    def _create_model(self, config: LLMConfig):
        """Instantiate the correct LLM backend, defaulting to ChatGPT on errors."""
        try:
            if config.provider == "openai":
                return OpenAILlm(model=config.model_name)
            if config.provider == "gemini":
                return Gemini(model=config.model_name)

            raise ValueError(f"Unsupported provider '{config.provider}'")
        except Exception as exc:
            logger.warning(
                "Failed to initialize model '%s': %s",
                config.identifier,
                exc,
                exc_info=True,
            )
            if config.identifier != self.default_id:
                return self._create_model(self.get_config(self.default_id))
            raise


llm_manager = LLMManager()

