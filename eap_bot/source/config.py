from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    GROQ_API_KEY: str = Field("")
    GOOGLE_API_KEY: str = Field("")

    LLM_PROVIDER: str = Field("mistral")  # 'groq', 'gemini', or 'ollama'
    LLM_MODEL_NAME: str = Field("gemini-3.1-flash-lite")
    OLLAMA_BASE_URL: str = Field("http://localhost:11434")

    # Fallback LLM (used when primary hits rate limits / 429 errors)
    LLM_FALLBACK_PROVIDER: str | None = Field(default=None)  # e.g. 'groq'
    LLM_FALLBACK_MODEL_NAME: str | None = Field(default=None)  # e.g. 'llama3-70b-8192'

    MISTRAL_API_KEY: str = Field("")
    # Legacy / Server specific fields
    vectorstore_root: str = Field("./vectorstores")
    specs_output_root: str = Field("./specs_output")

    # Use an absolute path on Azure, e.g. /var/lib/eap/storage.
    # The relative default is intended only for local development.
    EAP_STORAGE_ROOT: str = Field("./projects")

    CHUNK_SIZE: int = Field(1000)
    CHUNK_OVERLAP: int = Field(200)
    MAX_UPLOAD_SIZE: int = Field(50 * 1024 * 1024)

    EXTRACTOR_CHUNK_TOKENS: int = Field(3000)
    EXTRACTOR_CHUNK_OVERLAP_TOKENS: int = Field(200)
    EXTRACTOR_MAX_PARALLEL: int = Field(2)

settings = Settings()
