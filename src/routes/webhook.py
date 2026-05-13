"""
/webhook/message endpoint.
Orchestrates: validate → normalise → classify → AI reply → respond.
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.models.schemas import InboundMessage, NormalisedMessage, WebhookResponse
from src.services.classifier import classify_query
from src.services.ai_service import get_ai_reply

router = APIRouter()


def _determine_action(confidence_score: float, query_type: str) -> str:
    """
    Determine the action based on confidence score and query type.

    Rules:
    - complaint → always escalate (human must handle)
    - confidence >= 0.85 → auto_send
    - 0.60 <= confidence < 0.85 → agent_review
    - confidence < 0.60 → escalate
    """
    if query_type == "complaint":
        return "escalate"
    if confidence_score >= 0.85:
        return "auto_send"
    if confidence_score >= 0.60:
        return "agent_review"
    return "escalate"


@router.post("/message", response_model=WebhookResponse, summary="Process an inbound guest message")
async def handle_message(payload: InboundMessage):
    """
    Receive a raw guest message, normalise it, classify the query type,
    generate an AI-drafted reply via Claude, and return the result
    with a confidence score and recommended action.
    """
    try:
        # 1. Classify query type from raw message text
        query_type = classify_query(payload.message)

        # 2. Normalise into unified schema
        message_id = str(uuid.uuid4())
        normalised = NormalisedMessage(
            message_id=message_id,
            source=payload.source,
            guest_name=payload.guest_name,
            message_text=payload.message,
            timestamp=payload.timestamp,
            booking_ref=payload.booking_ref,
            property_id=payload.property_id,
            query_type=query_type,
        )

        # 3. Get AI-drafted reply and confidence score
        drafted_reply, confidence_score = await get_ai_reply(normalised)

        # 4. Determine recommended action
        action = _determine_action(confidence_score, query_type)

        # 5. Return structured response
        return WebhookResponse(
            message_id=message_id,
            query_type=query_type,
            drafted_reply=drafted_reply,
            confidence_score=confidence_score,
            action=action,
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )
