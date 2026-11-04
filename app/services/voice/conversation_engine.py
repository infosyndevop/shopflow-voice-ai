"""Conversation State and Dialog Management Engine.

Maintains multi-turn context scoped strictly to (tenant_id, session_id).
Handles:
- Adding items
- Correcting products or quantities
- Resolving pending clarifications
- Removing items
- Enforcing request idempotency to prevent duplicate item insertion on retries.
"""

import time
import re
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import logger
from app.schemas.voice_schemas import ItemInterpretation, InterpretationResponse, ItemStatus


# Conversational command regex triggers
REMOVE_TRIGGERS = re.compile(
    r"\b(?:remove|delete|cancel|clear|വേണ്ട|കളയുക|வேண்டாம்|நீக்கு)\b",
    re.IGNORECASE
)
CORRECTION_TRIGGERS = re.compile(
    r"\b(?:not|instead|change|correct|മാറ്റുക|மாற்று|അല്ല)\b",
    re.IGNORECASE
)


class ConversationalTurn(BaseModel):
    timestamp: float
    raw_transcript: str
    items: List[ItemInterpretation]
    pending_clarification: Optional[str] = None
    target_item_index: Optional[int] = None


class SessionState(BaseModel):
    tenant_id: str
    session_id: str
    last_updated: float
    items: List[ItemInterpretation] = Field(default_factory=list)
    pending_clarification_item: Optional[ItemInterpretation] = None


class ConversationEngine:
    """Session-isolated dialog management with idempotency caching."""

    def __init__(self):
        # Key: (tenant_id, session_id) -> SessionState
        self._sessions: Dict[Tuple[str, str], SessionState] = {}
        # Key: (tenant_id, idempotency_key) -> (timestamp, InterpretationResponse)
        self._idempotency_cache: Dict[Tuple[str, str], Tuple[float, InterpretationResponse]] = {}

    def _cleanup_expired(self):
        """Purges sessions and idempotency records older than TTL."""
        now = time.time()
        expired_sessions = [
            k for k, v in self._sessions.items()
            if now - v.last_updated > settings.CONVERSATION_SESSION_TTL_SECONDS
        ]
        for k in expired_sessions:
            del self._sessions[k]

        expired_idempotency = [
            k for k, (ts, _) in self._idempotency_cache.items()
            if now - ts > settings.CONVERSATION_SESSION_TTL_SECONDS
        ]
        for k in expired_idempotency:
            del self._idempotency_cache[k]

    def get_cached_idempotent_response(
        self, tenant_id: str, idempotency_key: Optional[str]
    ) -> Optional[InterpretationResponse]:
        """Returns previously computed response if the same request key is retried."""
        if not idempotency_key:
            return None
        self._cleanup_expired()
        cache_key = (tenant_id, idempotency_key)
        cached = self._idempotency_cache.get(cache_key)
        if cached:
            logger.info(f"Idempotency hit for tenant {tenant_id}, key {idempotency_key}")
            return cached[1]
        return None

    def store_idempotent_response(
        self, tenant_id: str, idempotency_key: Optional[str], response: InterpretationResponse
    ):
        """Stores response for idempotency verification."""
        if not idempotency_key:
            return
        if len(self._idempotency_cache) >= settings.IDEMPOTENCY_CACHE_SIZE:
            self._cleanup_expired()
        cache_key = (tenant_id, idempotency_key)
        self._idempotency_cache[cache_key] = (time.time(), response)

    def get_or_create_session(self, tenant_id: str, session_id: Optional[str]) -> Tuple[str, SessionState]:
        """Retrieves or initializes a session strictly bound to tenant_id."""
        self._cleanup_expired()
        now = time.time()
        sid = session_id or f"sess_{int(now * 1000)}"
        key = (tenant_id, sid)
        if key not in self._sessions:
            self._sessions[key] = SessionState(
                tenant_id=tenant_id,
                session_id=sid,
                last_updated=now,
            )
        else:
            self._sessions[key].last_updated = now
        return (sid, self._sessions[key])

    def detect_intent(self, text: str) -> str:
        """Determines if the phrase is a modification, deletion, clarification, or add command."""
        if REMOVE_TRIGGERS.search(text):
            return "remove"
        if CORRECTION_TRIGGERS.search(text):
            return "correct"
        return "add"

    def handle_pending_clarification(
        self,
        session: SessionState,
        text: str,
        new_items: List[ItemInterpretation]
    ) -> Optional[ItemInterpretation]:
        """If the session had an item waiting for clarification (e.g. variant or quantity),

        attempts to update and resolve only that pending item.
        """
        if not session.pending_clarification_item:
            return None

        pending = session.pending_clarification_item
        # If new items produced an updated verified variant or quantity
        if new_items:
            for item in new_items:
                if item.variant_id or item.quantity:
                    if item.variant_id:
                        pending.variant_id = item.variant_id
                        pending.variant_name = item.variant_name
                    if item.quantity:
                        pending.quantity = item.quantity
                        pending.unit = item.unit or pending.unit
                    pending.status = ItemStatus.VERIFIED
                    pending.clarification_prompt = None
                    session.pending_clarification_item = None
                    return pending

        return None

