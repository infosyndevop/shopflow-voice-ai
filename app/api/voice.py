"""Voice processing and interpretation endpoints."""

import base64
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, Header, Request, status

from app.api.health import increment_request_counter
from app.core.config import settings
from app.core.errors import (
    AudioPayloadTooLargeError,
    InvalidAudioError,
    ModelNotReadyError,
)
from app.core.logging import logger
from app.schemas.voice_schemas import (
    AudioTranscribeRequest,
    AudioTranscribeResponse,
    CandidateProductOption,
    InterpretationRequest,
    InterpretationResponse,
    InterpretationStatus,
    ItemInterpretation,
    ItemStatus,
)
from app.security.service_auth import TenantSecurityContext, get_tenant_context
from app.services.catalogue import get_catalogue_provider
from app.services.voice.confidence_engine import ConfidenceEngine
from app.services.voice.conversation_engine import ConversationEngine
from app.services.voice.language_normalizer import LanguageNormalizer
from app.services.voice.product_matcher import ProductMatcher
from app.services.voice.quantity_parser import QuantityParser
from app.services.voice.sku_matcher import SkuMatcher
from app.services.voice.speech_recognition import model_manager
from app.services.voice.variant_matcher import VariantMatcher

router = APIRouter(prefix="/api/v1/voice", tags=["Voice AI"])

# Module-level conversation state manager
conversation_engine = ConversationEngine()


@router.post(
    "/transcribe",
    response_model=AudioTranscribeResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe audio payload to text with tenant authorization"
)
async def transcribe_audio(
    payload: AudioTranscribeRequest,
    security_ctx: TenantSecurityContext = Depends(get_tenant_context),
):
    """Receives validated audio base64, authenticates service, and transcribes speech."""
    increment_request_counter()

    # Decode base64 audio payload
    try:
        audio_bytes = base64.b64decode(payload.audio_base64)
    except Exception as exc:
        raise InvalidAudioError("Base64 audio decoding failed: malformed payload") from exc

    if not audio_bytes:
        raise InvalidAudioError("Decoded audio payload is empty")

    if len(audio_bytes) > settings.MAX_AUDIO_SIZE_BYTES:
        raise AudioPayloadTooLargeError(
            f"Audio size ({len(audio_bytes)} bytes) exceeds maximum limit ({settings.MAX_AUDIO_SIZE_BYTES} bytes)"
        )

    # Perform transcription
    result = await model_manager.transcribe_audio(
        audio_bytes=audio_bytes,
        mime_type=payload.mime_type,
        language_hint=payload.language_hint
    )
    return result


async def _process_item_segment(
    segment_text: str,
    tenant_id: str,
    catalogue_provider,
    is_authenticated: bool,
) -> Tuple[Optional[ItemInterpretation], Optional[str]]:
    """Processes a single item segment into an ItemInterpretation or returns it as unmatched."""
    normalized_segment = LanguageNormalizer.normalize(segment_text)

    # 1. Check for SKU in segment
    sku_result = await SkuMatcher.match_sku(
        text=normalized_segment,
        tenant_id=tenant_id,
        catalogue_provider=catalogue_provider
    )

    clean_text = sku_result.clean_text if sku_result.extracted_sku else normalized_segment

    # 2. Quantity, Package Size, and Price Reference Parsing
    qty_result = QuantityParser.parse(clean_text)

    # Text remaining after quantity and package-size extraction
    product_search_text = qty_result.remaining_text.strip()

    # 3. Product Resolution
    matched_product = None
    product_score = 0.0
    product_candidates = []
    clarification_prompt = None

    if sku_result.matched_product:
        # SKU lookup succeeded
        matched_product = sku_result.matched_product
        product_score = 1.0

        # Disagreement check between SKU and spoken name
        if product_search_text:
            spoken_candidates = await ProductMatcher.find_candidates(
                product_search_text, tenant_id, catalogue_provider
            )
            if spoken_candidates:
                top_spoken = spoken_candidates[0]
                if top_spoken.product.product_id != matched_product.product_id:
                    sku_result.is_conflict = True
                    sku_result.conflict_reason = (
                        f"Spoken product '{top_spoken.product.canonical_name}' contradicts SKU '{sku_result.extracted_sku}' ({matched_product.canonical_name})"
                    )
    elif product_search_text:
        # Match product name from text
        match_result = await ProductMatcher.match_product(
            product_search_text, tenant_id, catalogue_provider
        )
        matched_product = match_result.product
        product_score = match_result.confidence
        product_candidates = match_result.candidates
        clarification_prompt = match_result.clarification_prompt

    # 4. Variant Resolution
    matched_variant = None
    variant_matched = False
    has_multiple_variants = False

    if matched_product:
        has_multiple_variants = len([v for v in matched_product.variants if v.is_active]) > 1
        if sku_result.matched_variant:
            matched_variant = sku_result.matched_variant
            variant_matched = True
        else:
            v_result = VariantMatcher.match_variant(
                product=matched_product,
                package_size=qty_result.package_size,
                sku=sku_result.extracted_sku,
                spoken_text=segment_text
            )
            matched_variant = v_result.variant
            variant_matched = (matched_variant is not None)
            if v_result.clarification_required:
                clarification_prompt = clarification_prompt or v_result.clarification_prompt

    # 5. Confidence Evaluation
    rejection_reason = None
    if sku_result.is_conflict:
        rejection_reason = sku_result.conflict_reason

    conf_metrics = ConfidenceEngine.evaluate_item(
        speech_quality=0.95,
        product_score=product_score,
        variant_matched=variant_matched,
        has_multiple_variants=has_multiple_variants,
        quantity=qty_result.quantity,
        quantity_ambiguous=qty_result.is_ambiguous,
        has_sku_conflict=sku_result.is_conflict,
        is_tenant_verified=is_authenticated,
        rejection_reason=rejection_reason,
    )

    candidate_options = [
        CandidateProductOption(
            product_id=c.product.product_id,
            product_name=c.product.canonical_name,
            sku=c.product.variants[0].sku if c.product.variants else None,
            variant_name=c.product.variants[0].variant_name if c.product.variants else None,
            match_score=c.match_score
        )
        for c in product_candidates
    ]

    if matched_product or product_candidates:
        item_interp = ItemInterpretation(
            product_id=matched_product.product_id if matched_product else None,
            product_name=matched_product.canonical_name if matched_product else None,
            variant_id=matched_variant.variant_id if matched_variant else None,
            variant_name=matched_variant.variant_name if matched_variant else None,
            sku=matched_variant.sku if matched_variant else sku_result.extracted_sku,
            quantity=qty_result.quantity,
            unit=qty_result.unit or (matched_variant.unit if matched_variant else (matched_product.default_unit if matched_product else "piece")),
            package_size=qty_result.package_size or (matched_variant.package_size if matched_variant else None),
            price_reference=qty_result.price_reference,
            product_confidence=conf_metrics.product_confidence,
            quantity_confidence=conf_metrics.quantity_confidence,
            status=conf_metrics.status,
            clarification_prompt=clarification_prompt or conf_metrics.rejection_reason,
            candidate_options=candidate_options
        )
        return (item_interp, None)
    else:
        return (None, segment_text)


@router.post(
    "/interpret",
    response_model=InterpretationResponse,
    status_code=status.HTTP_200_OK,
    summary="Interpret spoken product names, SKUs, variants, and quantities"
)
async def interpret_voice(
    payload: InterpretationRequest,
    security_ctx: TenantSecurityContext = Depends(get_tenant_context),
):
    """Processes transcript text into verified retail billing candidates.

    Guarantees:
    - Supports multiple distinct products in a single compound utterance.
    - Never silently selects an uncertain product.
    - Never silently assumes quantity is 1 when unclear.
    - Preserves SKU leading zeros exactly.
    - Isolates price references from order quantities.
    - Scoped strictly to authenticated tenant catalogue.
    """
    increment_request_counter()
    tenant_id = security_ctx.tenant_id

    # 1. Enforce Idempotency to prevent duplicate bill item addition
    cached_resp = conversation_engine.get_cached_idempotent_response(tenant_id, payload.idempotency_key)
    if cached_resp:
        return cached_resp

    # 2. Get or create session context
    session_id, session = conversation_engine.get_or_create_session(tenant_id, payload.session_id)
    catalogue_provider = get_catalogue_provider()

    raw_transcript = payload.transcript.strip()
    normalized_transcript = LanguageNormalizer.normalize(raw_transcript)

    if not raw_transcript:
        return InterpretationResponse(
            status=InterpretationStatus.UNMATCHED,
            transcript="",
            normalized_transcript="",
            items=[],
            unmatched_phrases=[],
            session_id=session_id,
            request_id=security_ctx.request_id,
        )

    # 3. Multi-turn Intent Detection (remove, correct, add)
    intent = conversation_engine.detect_intent(raw_transcript)

    # 4. Split compound utterance into candidate item segments
    segments = conversation_engine.split_utterance(raw_transcript)

    items: List[ItemInterpretation] = []
    unmatched_phrases: List[str] = []

    for seg in segments:
        item_interp, unmatched_txt = await _process_item_segment(
            segment_text=seg,
            tenant_id=tenant_id,
            catalogue_provider=catalogue_provider,
            is_authenticated=security_ctx.is_authenticated,
        )
        if item_interp:
            items.append(item_interp)
        elif unmatched_txt:
            unmatched_phrases.append(unmatched_txt)

    # 5. Multi-turn Intent and Clarification Handling
    if intent == "remove" and items:
        for it in items:
            it.status = ItemStatus.REJECTED
            it.clarification_prompt = "Item removed by employee voice command"
    elif intent == "correct" and items:
        conversation_engine.handle_correction(session, items)

    # If session has pending clarification, attempt resolution
    if session.pending_clarification_item:
        conversation_engine.handle_pending_clarification(session, raw_transcript, items)

    # Update session items for verified items
    for it in items:
        if it.status == ItemStatus.VERIFIED:
            session.items.append(it)
            if session.pending_clarification_item and session.pending_clarification_item.product_id == it.product_id:
                session.pending_clarification_item = None
        elif it.status == ItemStatus.NEEDS_CLARIFICATION:
            session.pending_clarification_item = it

    # 6. Overall status determination
    if items:
        overall_status = ConfidenceEngine.derive_overall_status([it.status for it in items])
        # If all parsed items are verified but some phrases were unresolved, ask for clarification
        if unmatched_phrases and overall_status == InterpretationStatus.VERIFIED:
            overall_status = InterpretationStatus.NEEDS_CLARIFICATION
    else:
        overall_status = InterpretationStatus.UNMATCHED

    clarification_required = (overall_status == InterpretationStatus.NEEDS_CLARIFICATION)
    clarification_question = None
    if clarification_required:
        clarifying_item = next((it for it in items if it.status == ItemStatus.NEEDS_CLARIFICATION), None)
        if clarifying_item and clarifying_item.clarification_prompt:
            clarification_question = clarifying_item.clarification_prompt
        elif unmatched_phrases:
            clarification_question = f"Could not recognize item phrase: '{unmatched_phrases[0]}'. Please clarify."
        else:
            clarification_question = "Could you please clarify the product or variant?"

    response = InterpretationResponse(
        status=overall_status,
        transcript=raw_transcript,
        normalized_transcript=normalized_transcript,
        items=items,
        unmatched_phrases=unmatched_phrases,
        clarification_required=clarification_required,
        clarification_question=clarification_question,
        session_id=session_id,
        request_id=security_ctx.request_id,
    )

    # Store for idempotency
    conversation_engine.store_idempotent_response(tenant_id, payload.idempotency_key, response)

    return response

