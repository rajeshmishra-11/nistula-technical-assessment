"""
webhook.py — POST /webhook/message Endpoint
============================================

This file defines the main (and only) business-logic route of the application.

WHAT THIS ENDPOINT DOES (step by step):
  1. RECEIVE   → FastAPI receives the JSON payload and validates it using InboundMessage schema.
                  If anything is wrong (bad source, missing field), it rejects with a 422 error
                  before this function is even called.

  2. CLASSIFY  → classify_query() reads the message text and determines the query type
                  (complaint, availability, pricing, etc.) using keyword/regex rules.

  3. NORMALISE → We create a NormalisedMessage — our unified internal format — that merges
                  the raw input with the query type we just determined and a fresh UUID.

  4. AI REPLY  → get_ai_reply() sends the normalised message to Claude (Anthropic API).
                  Claude drafts a guest-facing reply using a system prompt that includes
                  property context, tone guidelines, and the guest's query type.

  5. SCORE     → get_ai_reply() also returns a confidence_score (0.0–1.0) computed
                  deterministically based on query type, available context, and reply quality.

  6. ACTION    → _determine_action() translates the confidence score into an action:
                  auto_send / agent_review / escalate.

  7. RESPOND   → The WebhookResponse is serialised to JSON and returned to the caller.

ERROR HANDLING:
  - ValueError (e.g., missing API key): returns HTTP 500 with a clear message.
  - Any unexpected exception: returns HTTP 500 with the error detail.
"""

import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from src.models.schemas import InboundMessage, NormalisedMessage, WebhookResponse
from src.services.classifier import classify_query
from src.services.ai_service import get_ai_reply

# APIRouter lets us define routes in a separate file and mount them in main.py.
# The prefix ("/webhook") is added when we register this router in main.py.
router = APIRouter()


def _determine_action(confidence_score: float, query_type: str) -> str:
    """
    Translate a confidence score + query type into a recommended action string.

    Business Rules (in priority order):
      1. If query_type is "complaint" → ALWAYS escalate, no matter the score.
         Complaints require human empathy and judgment — AI should never auto-send.
      2. If confidence >= 0.85 → auto_send (AI is confident, safe to send directly).
      3. If confidence >= 0.60 → agent_review (AI has a good draft, but human should check).
      4. Otherwise            → escalate (AI is not confident enough to be useful).

    Args:
        confidence_score (float): A value between 0.0 and 1.0.
        query_type (str): The classified query type (e.g., "complaint", "pre_sales_pricing").

    Returns:
        str: One of "auto_send", "agent_review", or "escalate".
    """
    # Rule 1: Complaints ALWAYS go to a human — no exceptions
    if query_type == "complaint":
        return "escalate"

    # Rule 2: High confidence → safe to send automatically
    if confidence_score >= 0.85:
        return "auto_send"

    # Rule 3: Medium confidence → let an agent review first
    if confidence_score >= 0.60:
        return "agent_review"

    # Rule 4: Low confidence → escalate to human handling
    return "escalate"


@router.post(
    "/message",
    response_model=WebhookResponse,
    summary="Process an inbound guest message",
    description=(
        "Receives a raw guest message from any supported channel, classifies the query type, "
        "generates an AI-drafted reply using Claude, and returns the reply with a confidence "
        "score and recommended action (auto_send / agent_review / escalate)."
    ),
)
async def handle_message(payload: InboundMessage):
    """
    Main webhook handler — orchestrates the full message processing pipeline.

    FastAPI automatically validates `payload` against InboundMessage before calling this.
    If validation fails (e.g., invalid source channel), FastAPI returns 422 automatically.

    Args:
        payload (InboundMessage): The validated inbound message from the webhook caller.

    Returns:
        WebhookResponse: The AI-drafted reply, confidence score, and recommended action.

    Raises:
        HTTPException 500: If the Anthropic API key is missing or any unexpected error occurs.
    """
    try:
        # ── Step 1: Classify the query type ──────────────────────────────────
        # classifier.py uses regex pattern matching (no API call needed).
        # Returns one of: pre_sales_availability, pre_sales_pricing, post_sales_checkin,
        #                 special_request, complaint, general_enquiry
        query_type = classify_query(payload.message)

        # ── Step 2: Normalise into our unified internal schema ────────────────
        # Generate a UUID to uniquely identify this message throughout the system.
        # In production, this ID would be used to store the message in the database.
        message_id = str(uuid.uuid4())

        normalised = NormalisedMessage(
            message_id=message_id,
            source=payload.source,
            guest_name=payload.guest_name,
            message_text=payload.message,
            timestamp=payload.timestamp,
            booking_ref=payload.booking_ref,      # May be None — that's fine
            property_id=payload.property_id,      # May be None — AI falls back to generic context
            query_type=query_type,
        )

        # ── Step 3: Generate AI reply + compute confidence score ──────────────
        # get_ai_reply() is async because Anthropic's API call is I/O-bound.
        # It returns a tuple: (reply_text: str, confidence_score: float)
        drafted_reply, confidence_score = await get_ai_reply(normalised)

        # ── Step 4: Determine the recommended action ──────────────────────────
        # Converts confidence_score + query_type → "auto_send" / "agent_review" / "escalate"
        action = _determine_action(confidence_score, query_type)

        # ── Step 5: Return the structured response ────────────────────────────
        return WebhookResponse(
            message_id=message_id,
            query_type=query_type,
            drafted_reply=drafted_reply,
            confidence_score=confidence_score,
            action=action,
        )

    except ValueError as e:
        # ValueError is raised by ai_service.py if ANTHROPIC_API_KEY is not set.
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        # Catch-all for any unexpected errors (network issues, API failures, etc.)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )
