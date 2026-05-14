"""
schemas.py — Pydantic Request / Response Models
================================================

This file defines the data shapes (schemas) for:
  1. InboundMessage  — what we RECEIVE from the webhook caller (raw guest message)
  2. NormalisedMessage — our internal unified format after we process the raw message
  3. WebhookResponse  — what we RETURN to the caller (AI reply + metadata)

Why Pydantic?
  FastAPI uses Pydantic to automatically:
    - Validate incoming JSON (reject bad data with a 422 error before it hits our logic)
    - Serialize outgoing responses to JSON
    - Generate the interactive Swagger docs at /docs

Design principle:
  InboundMessage is intentionally minimal — we only ask for what the channel gives us.
  NormalisedMessage adds our own fields (message_id, query_type) after processing.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime


# ─────────────────────────────────────────────────────────────
# 1. SOURCE CHANNEL TYPE
# ─────────────────────────────────────────────────────────────
# All allowed message source channels.
# Using Literal means Pydantic will reject any value not in this list with a 422 error.
# Example: "source": "twitter" → rejected immediately, never reaches our business logic.

SourceChannel = Literal["whatsapp", "booking_com", "airbnb", "instagram", "direct"]


# ─────────────────────────────────────────────────────────────
# 2. QUERY TYPE
# ─────────────────────────────────────────────────────────────
# The six categories a guest message can be classified into.
# Assigned by classifier.py based on keyword/pattern matching.
#
# pre_sales_availability — Guest asking if dates are available before booking
# pre_sales_pricing      — Guest asking about rates/costs before booking
# post_sales_checkin     — Guest asking about check-in logistics (already booked)
# special_request        — Guest requesting extras (airport pickup, birthday decor, etc.)
# complaint              — Guest expressing dissatisfaction or demanding refund
# general_enquiry        — Everything else (pets, parking, amenities, etc.)

QueryType = Literal[
    "pre_sales_availability",
    "pre_sales_pricing",
    "post_sales_checkin",
    "special_request",
    "complaint",
    "general_enquiry",
]


# ─────────────────────────────────────────────────────────────
# 3. ACTION TYPE
# ─────────────────────────────────────────────────────────────
# The recommended next action based on confidence score and query type.
#
# auto_send    — AI reply is confident enough to send directly to guest (score >= 0.85)
# agent_review — AI reply needs a human to check before sending (score 0.60–0.84)
# escalate     — AI is not confident, OR it's a complaint → always hand off to a human

ActionType = Literal["auto_send", "agent_review", "escalate"]


# ─────────────────────────────────────────────────────────────
# 4. INBOUND MESSAGE (Request Body)
# ─────────────────────────────────────────────────────────────
# This is what the webhook caller sends us.
# Represents a raw, unprocessed guest message from any channel.

class InboundMessage(BaseModel):
    """Raw message received from any source channel via POST /webhook/message."""

    source: SourceChannel = Field(
        ...,
        description="The channel the message came from. Must be one of: whatsapp, booking_com, airbnb, instagram, direct."
    )
    guest_name: str = Field(
        ...,
        description="Full name of the guest as provided by the channel."
    )
    message: str = Field(
        ...,
        description="The raw text of the guest's message. This is what gets classified and sent to Claude."
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of when the message was sent. Example: '2026-05-14T10:30:00Z'."
    )
    booking_ref: Optional[str] = Field(
        None,
        description="Booking reference number if the guest already has a reservation. Example: 'NIS-2024-0891'. Optional."
    )
    property_id: Optional[str] = Field(
        None,
        description="The property identifier the guest is enquiring about. Example: 'villa-b1'. Optional — used to look up property context for the AI."
    )

    # model_config provides an example that appears in the Swagger UI /docs
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source": "whatsapp",
                "guest_name": "Rahul Sharma",
                "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
                "timestamp": "2026-05-05T10:30:00Z",
                "booking_ref": "NIS-2024-0891",
                "property_id": "villa-b1",
            }
        }
    )


# ─────────────────────────────────────────────────────────────
# 5. NORMALISED MESSAGE (Internal Schema)
# ─────────────────────────────────────────────────────────────
# After receiving an InboundMessage, we enrich it with:
#   - A unique message_id (UUID) we generate ourselves
#   - The query_type we classified it into
# This is the unified internal format passed between services.

class NormalisedMessage(BaseModel):
    """Unified internal message schema — created by the webhook handler after classification."""

    message_id: str = Field(..., description="UUID we generate to uniquely identify this message.")
    source: str = Field(..., description="Source channel (copied from InboundMessage).")
    guest_name: str = Field(..., description="Guest's full name.")
    message_text: str = Field(..., description="The raw guest message text.")
    timestamp: str = Field(..., description="Original message timestamp from the channel.")
    booking_ref: Optional[str] = Field(None, description="Booking reference, if provided.")
    property_id: Optional[str] = Field(None, description="Property ID, if provided.")
    query_type: QueryType = Field(..., description="The classified query type assigned by classifier.py.")


# ─────────────────────────────────────────────────────────────
# 6. WEBHOOK RESPONSE (Response Body)
# ─────────────────────────────────────────────────────────────
# This is what we return to the webhook caller after processing.

class WebhookResponse(BaseModel):
    """
    Final response returned by POST /webhook/message.

    Contains:
      - message_id      → unique ID to track this message
      - query_type      → how the message was classified
      - drafted_reply   → what Claude drafted as a guest-facing reply
      - confidence_score→ our calculated confidence (0.0 = no confidence, 1.0 = fully confident)
      - action          → what should happen next (auto_send / agent_review / escalate)
    """

    message_id: str = Field(..., description="The UUID assigned to this message.")
    query_type: QueryType = Field(..., description="Classified query category.")
    drafted_reply: str = Field(..., description="The AI-drafted reply text, ready to review or send.")
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score between 0.0 and 1.0. Higher = more confident the AI reply is correct."
    )
    action: ActionType = Field(
        ...,
        description=(
            "Recommended next action: "
            "'auto_send' (score >= 0.85), "
            "'agent_review' (score 0.60–0.84), "
            "'escalate' (score < 0.60 or query_type is 'complaint')."
        )
    )
