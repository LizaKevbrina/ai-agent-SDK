"""
Application Settings
Manages environment variables and configuration
"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application configuration from environment variables"""
    
    # Application
    APP_NAME: str = "AI Real Estate Agent"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"
    
    # API Keys - LLM Providers
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    YANDEX_API_KEY: Optional[str] = None
    YANDEX_FOLDER_ID: Optional[str] = None
    
    # Database
    POSTGRES_URL: str = "postgresql://ai_user:password@postgres:5432/ai_db"
    
    # Vector Store
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Redis
    REDIS_URL: str = "redis://redis:6379"
    
    # LLM Configuration
    DEFAULT_LLM_MODEL: str = "gpt-4"
    TEMPERATURE: float = 0.7
    MAX_TOKENS: int = 2000
    
    # RAG Configuration
    SIMILARITY_THRESHOLD: float = 0.7
    RAG_TOP_K: int = 5
    
    # Memory Configuration
    MEMORY_WINDOW_SIZE: int = 40
    DEFAULT_PROMPT_VERSION: str = "v1"
    
    # Circuit Breaker
    CIRCUIT_BREAKER_FAIL_MAX: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60
    
    # Monitoring
    PROMETHEUS_PORT: int = 9090
    SENTRY_DSN: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True

    # Add secrets file support (from original secrets_helper.py)
            
    def load_secret(cls, env_var: str, fallback: str) -> str:
 
       """Load from file or env variable"""

        file_path = os.getenv(f"{env_var}_FILE")

        if file_path and os.path.exists(file_path):

            with open(file_path) as f:

                return f.read().strip()

        return os.getenv(fallback, "")

    
# Override fields to use secrets

    OPENAI_API_KEY: str = Field(

        default_factory=lambda: Settings.load_secret("OPENAI_API_KEY", "OPENAI_API_KEY")

    )

# Global settings instance
settings = Settings()
