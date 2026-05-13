"""
Claude AI service.
Builds the system prompt with property context and query type,
then calls the Anthropic API to get a drafted guest reply.
Also computes and returns the confidence score.
"""

import os
import anthropic
from src.models.schemas import NormalisedMessage, QueryType
from src.services.property_context import get_property_context


# ─────────────────────────────────────────────
# Tone & Style Instructions per Query Type
# ─────────────────────────────────────────────

_TONE_GUIDE: dict[QueryType, str] = {
    "pre_sales_availability": (
        "Be warm, enthusiastic, and helpful. Confirm availability clearly. "
        "Invite the guest to proceed with a booking and offer to assist."
    ),
    "pre_sales_pricing": (
        "Be transparent and friendly. Provide the rate breakdown clearly. "
        "Mention any extras (e.g., extra guests). Invite them to book."
    ),
    "post_sales_checkin": (
        "Be welcoming and reassuring. The guest has already booked — make them "
        "feel taken care of. Answer specifically and offer additional help."
    ),
    "special_request": (
        "Acknowledge the request with enthusiasm. Be helpful and realistic. "
        "If you need more details, ask one specific question."
    ),
    "complaint": (
        "Express genuine empathy immediately. Do not be defensive. Acknowledge "
        "the issue, apologise sincerely, and explain what will happen next. "
        "Escalate to a human as appropriate. Never dismiss the complaint."
    ),
    "general_enquiry": (
        "Be friendly and informative. Answer what you can from property context. "
        "Offer to help further."
    ),
}


def _build_system_prompt(message: NormalisedMessage, property_context: str) -> str:
    tone = _TONE_GUIDE.get(message.query_type, _TONE_GUIDE["general_enquiry"])
    return f"""You are a professional and warm guest relations assistant for Nistula, a luxury villa hospitality company in Goa, India.

PROPERTY CONTEXT:
{property_context}

GUEST INFORMATION:
- Name: {message.guest_name}
- Source channel: {message.source}
- Booking reference: {message.booking_ref or 'Not provided'}
- Query type: {message.query_type}

TONE & STYLE GUIDE:
{tone}

INSTRUCTIONS:
- Write a single, concise guest-facing reply (2–4 short paragraphs max).
- Address the guest by their first name.
- Be specific — use the property context to give real answers, not generic ones.
- Do NOT include subject lines, greetings like "Dear Sir/Madam", or sign-offs.
- Do NOT make up information that isn't in the property context.
- Sound human, warm, and professional — not robotic.
- If the query is a complaint, begin with a sincere apology.
"""


def _compute_confidence(message: NormalisedMessage, reply: str) -> float:
    """
    Confidence scoring logic:

    Base score is determined by query type clarity:
    - Complaints always get low confidence (require human oversight).
    - Known, data-rich query types start at high confidence.
    - General enquiries start mid-range.

    Penalties:
    - Missing booking_ref for post-sales queries: -0.10
    - Missing property_id: -0.05
    - Very short reply (< 50 chars): -0.15 (AI may have failed)
    - Reply contains "I don't know" or "not sure": -0.20

    Score is clamped to [0.0, 1.0].
    """
    base_scores: dict[QueryType, float] = {
        "pre_sales_availability": 0.92,
        "pre_sales_pricing": 0.90,
        "post_sales_checkin": 0.88,
        "special_request": 0.78,
        "general_enquiry": 0.75,
        "complaint": 0.45,  # Always escalate complaints
    }

    score = base_scores.get(message.query_type, 0.70)

    # Penalties
    if message.query_type == "post_sales_checkin" and not message.booking_ref:
        score -= 0.10
    if not message.property_id:
        score -= 0.05
    if len(reply) < 50:
        score -= 0.15
    lowered_reply = reply.lower()
    if any(phrase in lowered_reply for phrase in ["i don't know", "not sure", "i'm not certain", "i cannot"]):
        score -= 0.20

    return round(max(0.0, min(1.0, score)), 2)


async def get_ai_reply(message: NormalisedMessage) -> tuple[str, float]:
    """
    Call the Claude API and return (drafted_reply, confidence_score).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment variables.")

    property_context = get_property_context(message.property_id)
    system_prompt = _build_system_prompt(message, property_context)

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": message.message_text,
            }
        ],
    )

    reply_text = response.content[0].text.strip()
    confidence = _compute_confidence(message, reply_text)

    return reply_text, confidence
