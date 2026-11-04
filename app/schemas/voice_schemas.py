"""Pydantic schemas for requests, responses, item interpretations, and health checks."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class InterpretationStatus(str, Enum):
    VERIFIED = "verified"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    UNMATCHED = "unmatched"
    UNAVAILABLE = "unavailable"
    SERVICE_UNAVAILABLE = "service_unavailable"


class ItemStatus(str, Enum):
    VERIFIED = "verified"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    UNMATCHED = "unmatched"
    UNAVAILABLE = "unavailable"


class ModelLifecycleState(str, Enum):
    NOT_INITIALIZED = "not_initialized"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


# Audio Transcription Models
class AudioTranscribeRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded raw audio or wav/mp3 data")
    mime_type: str = Field(default="audio/wav", description="Audio MIME type, e.g. audio/wav, audio/mpeg")
    language_hint: Optional[str] = Field(default="mixed", description="ml, ta, en, or mixed")
    duration_seconds: Optional[float] = Field(default=None, description="Optional client-reported duration in seconds")

    @field_validator("audio_base64")
    @classmethod
    def validate_audio_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Audio payload cannot be empty")
        return v


class AudioTranscribeResponse(BaseModel):
    transcript: str
    detected_language: str = "mixed"
    confidence: float = Field(ge=0.0, le=1.0)
    duration_seconds: Optional[float] = None
    status: str = "success"


# Voice Interpretation Models
class InterpretationRequest(BaseModel):
    transcript: str = Field(..., min_length=1, max_length=500, description="Raw transcription text")
    session_id: Optional[str] = Field(default=None, description="Conversational session ID for multi-turn bill editing")
    idempotency_key: Optional[str] = Field(default=None, description="Unique client request ID to avoid duplicate billing")
    language_hint: Optional[str] = Field(default=None, description="ml, ta, en, mixed")

    @field_validator("transcript")
    @classmethod
    def validate_transcript(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Transcript cannot be empty or whitespace only")
        return cleaned


class CandidateProductOption(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    variant_name: Optional[str] = None
    match_score: float = Field(ge=0.0, le=1.0)


class ItemInterpretation(BaseModel):
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    variant_id: Optional[str] = None
    variant_name: Optional[str] = None
    sku: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    package_size: Optional[str] = None
    price_reference: Optional[float] = None
    product_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quantity_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: ItemStatus
    clarification_prompt: Optional[str] = None
    candidate_options: List[CandidateProductOption] = Field(default_factory=list)


class InterpretationResponse(BaseModel):
    status: InterpretationStatus
    transcript: str
    normalized_transcript: str
    items: List[ItemInterpretation]
    unmatched_phrases: List[str] = Field(default_factory=list)
    clarification_required: bool = False
    clarification_question: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None


# Health Check Models
class LiveStatusResponse(BaseModel):
    status: str = "alive"
    timestamp: str


class ReadyStatusResponse(BaseModel):
    status: str = "ready"
    model_ready: bool
    catalogue_provider_ready: bool
    timestamp: str


class ModelStatusResponse(BaseModel):
    model_name: str
    state: ModelLifecycleState
    device: str
    is_ready: bool
    worker_concurrency: int


class DiagnosticsResponse(BaseModel):
    status: str
    version: str
    environment: str
    model_state: ModelLifecycleState
    uptime_seconds: float
    total_requests_processed: int
    memory_usage_mb: Optional[float] = None
