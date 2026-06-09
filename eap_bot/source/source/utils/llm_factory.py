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
            "max_retries": 0,
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
            "max_retries": 0,
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
            "max_retries": 0,
        }
        if require_json:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}

        return ChatMistralAI(**kwargs)


class RobustFallbackWrapper:
    def __init__(self, models):
        self.models = models

    def invoke(self, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        last_exception = None
        for i, model in enumerate(self.models):
            try:
                response = model.invoke(*args, **kwargs)
                content_lower = str(response.content).lower()
                
                # Custom check for non-HTTP quota errors
                if "quota" in content_lower or "rate limit" in content_lower or "429" in content_lower:
                    raise Exception(f"Model {i} returned quota error in text: {response.content[:50]}")
                    
                return response
            except Exception as e:
                logger.warning(f"LLM fallback triggered. Model {i} failed: {str(e)}")
                last_exception = e
                
        raise RuntimeError(f"All LLM fallbacks exhausted. Last error: {str(last_exception)}")


class MultiFallbackLLMStrategy(LLMStrategy):
    def __init__(self, primary: LLMStrategy, fallbacks: list[tuple[LLMStrategy, str]]):
        self._primary = primary
        self._fallbacks = fallbacks

    def get_model(self, temperature: float = 0.0, require_json: bool = False):
        primary_model = self._primary.get_model(temperature=temperature, require_json=require_json)
        
        models = [primary_model]
        original_model_name = settings.LLM_MODEL_NAME
        
        for strategy, model_name in self._fallbacks:
            settings.LLM_MODEL_NAME = model_name
            try:
                fallback_model = strategy.get_model(temperature=temperature, require_json=require_json)
                models.append(fallback_model)
            finally:
                settings.LLM_MODEL_NAME = original_model_name
                
        return RobustFallbackWrapper(models)


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

        if getattr(settings, "LLM_FALLBACKS", None):
            fallback_configs = settings.LLM_FALLBACKS.split(",")
            fallbacks = []
            for conf in fallback_configs:
                parts = conf.split(":")
                if len(parts) == 2:
                    provider, model_name = parts
                    fallbacks.append((_make_strategy(provider.strip()), model_name.strip()))
                    
            if fallbacks:
                return MultiFallbackLLMStrategy(primary, fallbacks)

        return primary
