from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    GROQ_API_KEY: str = Field("")
    
    LLM_PROVIDER: str = Field("groq") # 'groq' or 'ollama'
    LLM_MODEL_NAME: str = Field("llama-3.3-70b-versatile")
    OLLAMA_BASE_URL: str = Field("http://localhost:11434")

    DATABASE_URL: str = Field("sqlite:///./app.db")
    PROJECTS_DIR: str = Field("./projects")
    VECTORSTORE_ROOT: str = Field("./vectorstores")

    CHUNK_SIZE: int = Field(1000)
    CHUNK_OVERLAP: int = Field(200)
    MAX_UPLOAD_SIZE: int = Field(50 * 1024 * 1024)

    class Config:
        env_file = ".env"


settings = Settings()

Path(settings.PROJECTS_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.VECTORSTORE_ROOT).mkdir(parents=True, exist_ok=True)
