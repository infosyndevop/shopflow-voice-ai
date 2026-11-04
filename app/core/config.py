"""Application configuration using Pydantic Settings."""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Project metadata
    PROJECT_NAME: str = "CRYVEX ShopFlow Voice AI Backend"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", description="Environment: development, test, staging, production")
    DEBUG: bool = False

    # Security
    SERVICE_API_KEY: str = Field(
        default="test-service-key-cryvex-voice-secret-min32chars",
        description="Shared secret for service-to-service authentication"
    )
    SERVICE_HEADER_NAME: str = "X-Service-Key"
    TENANT_HEADER_NAME: str = "X-Tenant-ID"

    # Catalogue Integration
    CATALOGUE_PROVIDER_TYPE: str = Field(default="mock", description="'mock' or 'http'")
    SHOPFLOW_BACKEND_URL: Optional[str] = "http://localhost:8000"
    SHOPFLOW_INTERNAL_API_KEY: Optional[str] = None
    CATALOGUE_TIMEOUT_SECONDS: float = 3.0
    CATALOGUE_CACHE_TTL_SECONDS: int = 60

    # Speech Recognition Engine & Production Configuration (Section 11)
    SPEECH_PROVIDER: str = Field(default="mock", description="'mock' or 'sherpa_onnx'")
    ASR_LANGUAGE: str = Field(default="en", description="'ml', 'ta', or 'en'")
    ASR_MODEL_DIR: str = Field(default="models", description="Base directory containing onnx model files")
    ASR_NUM_THREADS: int = Field(default=1, description="Number of CPU threads for inference")
    ASR_MAX_AUDIO_SECONDS: float = Field(default=30.0, description="Max audio duration in seconds")
    ASR_MAX_CONCURRENT_REQUESTS: int = Field(default=1, description="Max concurrent inference requests")

    # Backward compatibility aliases
    SPEECH_PROVIDER_TYPE: str = Field(default="mock", description="Alias for SPEECH_PROVIDER")
    SPEECH_MODEL_NAME: str = "indicconformer-sherpa-onnx"
    SPEECH_MODEL_WARMUP_ON_STARTUP: bool = True
    MAX_AUDIO_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB
    MAX_AUDIO_DURATION_SECONDS: float = 30.0
    INFERENCE_TIMEOUT_SECONDS: float = 8.0

    # Business Logic Thresholds
    DEFAULT_MAX_QUANTITY: float = 500.0
    MAX_DECIMAL_PLACES: int = 3
    HIGH_CONFIDENCE_THRESHOLD: float = 0.85
    MEDIUM_CONFIDENCE_THRESHOLD: float = 0.60
    FUZZY_DISCOVERY_THRESHOLD: float = 75.0

    # Conversation and Idempotency
    CONVERSATION_SESSION_TTL_SECONDS: int = 600
    IDEMPOTENCY_CACHE_SIZE: int = 2000

    # Optional Database (non-authoritative)
    DATABASE_URL: Optional[str] = None


settings = Settings()

