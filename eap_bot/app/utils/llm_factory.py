from abc import ABC, abstractmethod
from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings

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


class LLMFactory:
    @staticmethod
    def create_strategy() -> LLMStrategy:
        provider = settings.LLM_PROVIDER.lower()
        if provider == "groq":
            return GroqStrategy()
        elif provider == "ollama":
            return OllamaStrategy()
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
