from abc import ABC, abstractmethod
from langchain_core.language_models.chat_models import BaseChatModel

from source.config import settings

class LLMStrategy(ABC):
    @abstractmethod
    def get_model(self, temperature: float = 0.0, require_json: bool = False) -> BaseChatModel:
        pass


class GroqStrategy(LLMStrategy):
    def get_model(self, temperature: float = 0.0, require_json: bool = False) -> BaseChatModel:
        from langchain_groq import ChatGroq
        
        kwargs = {
            "model": settings.LLM_MODEL_NAME,
            "api_key": settings.GROQ_API_KEY,
            "temperature": temperature,
            "max_retries": 6,
        }
        if require_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

        return ChatGroq(**kwargs)


class OllamaStrategy(LLMStrategy):
    def get_model(self, temperature: float = 0.0, require_json: bool = False) -> BaseChatModel:
        from langchain_ollama import ChatOllama
        
        kwargs = {
            "model": settings.LLM_MODEL_NAME,
            "base_url": settings.OLLAMA_BASE_URL,
            "temperature": temperature,
        }
        if require_json:
            kwargs["format"] = "json"
            
        return ChatOllama(**kwargs)


class GeminiStrategy(LLMStrategy):
    def get_model(self, temperature: float = 0.0, require_json: bool = False) -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        kwargs = {
            "model": settings.LLM_MODEL_NAME,
            "google_api_key": settings.GOOGLE_API_KEY,
            "temperature": temperature,
            "max_retries": 6,
        }
        if require_json:
            kwargs["model_kwargs"] = {"response_mime_type": "application/json"}

        return ChatGoogleGenerativeAI(**kwargs)

class MistralStrategy(LLMStrategy):
    def get_model(self, temperature: float = 0.0, require_json: bool = False) -> BaseChatModel:
        from langchain_mistralai import ChatMistralAI

        kwargs = {
            "model": settings.LLM_MODEL_NAME,
            "api_key": settings.MISTRAL_API_KEY,
            "temperature": temperature,
            "max_retries": 6,
        }
        if require_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

        return ChatMistralAI(**kwargs)


class FallbackLLMStrategy(LLMStrategy):
    """
    Wraps a primary and a fallback LLMStrategy using LangChain's .with_fallbacks().
    When the primary LLM raises an exception (e.g. 429 quota exceeded), LangChain
    will automatically retry the same call against the fallback model.
    Consumers (equipment_extractor, mapping_service, etc.) are fully unaware of this.
    """
    def __init__(self, primary: LLMStrategy, fallback: LLMStrategy, fallback_model_name: str):
        self._primary = primary
        self._fallback = fallback
        self._fallback_model_name = fallback_model_name

    def get_model(self, temperature: float = 0.0, require_json: bool = False) -> BaseChatModel:
        primary_model = self._primary.get_model(temperature=temperature, require_json=require_json)

        # Temporarily swap the model name so fallback uses its own model, not the primary's
        original_model_name = settings.LLM_MODEL_NAME
        settings.LLM_MODEL_NAME = self._fallback_model_name
        try:
            fallback_model = self._fallback.get_model(temperature=temperature, require_json=require_json)
        finally:
            settings.LLM_MODEL_NAME = original_model_name

        return primary_model.with_fallbacks([fallback_model])


def _make_strategy(provider: str) -> LLMStrategy:
    """Instantiate an LLMStrategy for a given provider name."""
    p = provider.lower()
    if p == "groq":
        return GroqStrategy()
    elif p == "ollama":
        return OllamaStrategy()
    elif p == "gemini":
        return GeminiStrategy()
    elif p == "mistral":
        return MistralStrategy()
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


class LLMFactory:
    @staticmethod
    def create_strategy() -> LLMStrategy:
        primary = _make_strategy(settings.LLM_PROVIDER)

        # If a fallback provider is configured, compose a FallbackLLMStrategy
        if settings.LLM_FALLBACK_PROVIDER and settings.LLM_FALLBACK_MODEL_NAME:
            fallback = _make_strategy(settings.LLM_FALLBACK_PROVIDER)
            return FallbackLLMStrategy(
                primary=primary,
                fallback=fallback,
                fallback_model_name=settings.LLM_FALLBACK_MODEL_NAME,
            )

        return primary
