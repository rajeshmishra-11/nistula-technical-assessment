"""
Pydantic models for request/response schema.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime


# ─────────────────────────────────────────────
# Inbound Webhook Payload (raw from channel)
# ─────────────────────────────────────────────

class InboundMessage(BaseModel):
    """Raw message received from any source channel."""
    source: Literal["whatsapp", "booking_com", "airbnb", "instagram", "direct"] = Field(
        ..., description="Source channel of the message"
    )
    guest_name: str = Field(..., description="Name of the guest")
    message: str = Field(..., description="The raw message text from the guest")
    timestamp: str = Field(..., description="ISO 8601 timestamp of when message was sent")
    booking_ref: Optional[str] = Field(None, description="Booking reference if available")
    property_id: Optional[str] = Field(None, description="Property identifier")

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


# ─────────────────────────────────────────────
# Query Type Classification
# ─────────────────────────────────────────────

QueryType = Literal[
    "pre_sales_availability",
    "pre_sales_pricing",
    "post_sales_checkin",
    "special_request",
    "complaint",
    "general_enquiry",
]

# ─────────────────────────────────────────────
# Unified Normalised Message Schema
# ─────────────────────────────────────────────

class NormalisedMessage(BaseModel):
    """Unified schema after normalising raw inbound message."""
    message_id: str = Field(..., description="UUID generated for this message")
    source: str = Field(..., description="Source channel")
    guest_name: str
    message_text: str
    timestamp: str
    booking_ref: Optional[str] = None
    property_id: Optional[str] = None
    query_type: QueryType = Field(..., description="Classified query type")


# ─────────────────────────────────────────────
# Webhook Response
# ─────────────────────────────────────────────

ActionType = Literal["auto_send", "agent_review", "escalate"]


class WebhookResponse(BaseModel):
    """Response returned by the /webhook/message endpoint."""
    message_id: str
    query_type: QueryType
    drafted_reply: str
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score between 0 and 1"
    )
    action: ActionType = Field(
        ...,
        description="auto_send (>0.85), agent_review (0.60-0.85), escalate (<0.60 or complaint)",
    )
