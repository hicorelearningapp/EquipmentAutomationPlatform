from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GROQ_API_KEY: str = Field("")

    LLM_PROVIDER: str = Field("groq")  # 'groq' or 'ollama'
    LLM_MODEL_NAME: str = Field("llama-3.3-70b-versatile")
    OLLAMA_BASE_URL: str = Field("http://localhost:11434")

    # Use an absolute path on Azure, e.g. /var/lib/eap/storage.
    # The relative default is intended only for local development.
    EAP_STORAGE_ROOT: str = Field("./runtime_storage")

    CHUNK_SIZE: int = Field(1000)
    CHUNK_OVERLAP: int = Field(200)
    MAX_UPLOAD_SIZE: int = Field(50 * 1024 * 1024)

    class Config:
        env_file = ".env"


settings = Settings()
