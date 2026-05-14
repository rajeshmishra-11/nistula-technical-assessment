"""
ai_service.py — Claude AI Integration & Confidence Scoring
===========================================================

This module is responsible for two things:
  1. DRAFTING A REPLY → Calls the Anthropic Claude API with a carefully crafted
                         system prompt and returns a guest-facing reply.
  2. SCORING CONFIDENCE → Calculates a deterministic confidence score (0.0–1.0)
                           that reflects how reliable the AI reply is.

─────────────────────────────────────────────────────────────────────────
PART A: AI REPLY DRAFTING
─────────────────────────────────────────────────────────────────────────

The system prompt sent to Claude contains three things:
  1. PROPERTY CONTEXT  — Real data about the villa (rates, wifi, check-in times, etc.)
                          from property_context.py. This grounds the reply in facts.
  2. GUEST INFORMATION — Name, source channel, booking ref, query type.
  3. TONE & STYLE GUIDE — Specific instructions on how to reply depending on the
                          query type (e.g., empathetic for complaints, enthusiastic
                          for availability queries).

The user prompt sent to Claude is simply the guest's raw message text.

─────────────────────────────────────────────────────────────────────────
PART B: CONFIDENCE SCORING
─────────────────────────────────────────────────────────────────────────

WHY NOT USE CLAUDE'S OWN CONFIDENCE?
  Claude's API does not return a reliable self-confidence value.
  Instead, we compute our OWN score deterministically based on:

  BASE SCORE (by query type):
    - pre_sales_availability: 0.92  → Factual, clear-cut answer
    - pre_sales_pricing:      0.90  → All rate data is in property context
    - post_sales_checkin:     0.88  → Check-in details are precise and known
    - special_request:        0.78  → May need human clarification
    - general_enquiry:        0.75  → Variable scope, answer may be incomplete
    - complaint:              0.45  → ALWAYS needs human judgment

  PENALTIES (applied on top of base score):
    - No booking_ref for post-sales query:          −0.10
      (We can't verify the guest has a real booking)
    - No property_id provided:                      −0.05
      (AI had to use generic context, less accurate)
    - Reply is very short (< 50 chars):             −0.15
      (Likely something went wrong with the API)
    - Reply contains uncertainty phrases:           −0.20
      ("I don't know", "not sure", "I cannot")

  FINAL: Score is clamped to [0.0, 1.0] and rounded to 2 decimal places.

─────────────────────────────────────────────────────────────────────────
TESTING WITHOUT AN API KEY:
─────────────────────────────────────────────────────────────────────────
  Set MOCK_AI=true in your .env file (or environment).
  The module will return deterministic mock replies per query type,
  which is how the pytest test suite works without hitting real Claude.
"""

import os
import anthropic
from src.models.schemas import NormalisedMessage, QueryType
from src.services.property_context import get_property_context


# ─────────────────────────────────────────────────────────────
# Tone Guide (per query type)
# ─────────────────────────────────────────────────────────────
# These instructions are embedded in the Claude system prompt.
# Each query type gets a specific tone to ensure appropriate responses.
# For example: complaints need empathy first; availability needs enthusiasm.

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
    """
    Build the system prompt that tells Claude how to behave for this message.

    The system prompt is the most important part of the Claude API call.
    It sets the persona, provides factual grounding (property context),
    and gives tone instructions tailored to the specific query type.

    Args:
        message (NormalisedMessage): The normalised message with query_type, guest_name, etc.
        property_context (str): The formatted property data from property_context.py.

    Returns:
        str: The complete system prompt string to send to Claude.
    """
    # Get the tone instruction for this query type
    # Fall back to general_enquiry tone if the type is somehow not in the guide
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
    Calculate a deterministic confidence score for the AI reply.

    This score represents how much we trust the AI's reply to be correct and complete.
    It is NOT Claude's own self-assessment — we compute it ourselves based on context quality.

    Scoring Logic:
      Start with a base score for the query type (see BASE_SCORES below).
      Then apply penalties for missing context or low-quality replies.
      Finally, clamp to [0.0, 1.0] and round to 2 decimal places.

    Args:
        message (NormalisedMessage): Used to check booking_ref, property_id, query_type.
        reply (str): The AI-generated reply text (used to check for quality signals).

    Returns:
        float: Confidence score between 0.0 and 1.0, rounded to 2 decimal places.
    """
    # Base confidence scores per query type
    # Higher = more predictable, data-driven answers; Lower = more human judgment needed
    base_scores: dict[QueryType, float] = {
        "pre_sales_availability": 0.92,  # Factual — is the date free or not?
        "pre_sales_pricing":      0.90,  # All rates are in the property context
        "post_sales_checkin":     0.88,  # Check-in info is exact and known
        "special_request":        0.78,  # May need clarification or human arrangements
        "general_enquiry":        0.75,  # Broad scope; answer may be partial
        "complaint":              0.45,  # Always needs human empathy and judgment
    }

    score = base_scores.get(message.query_type, 0.70)

    # ── Penalty 1: Post-sales query without a booking reference ──────────────
    # If a guest asks about check-in info but we can't verify they have a booking,
    # the AI is less reliable (it might be answering a non-guest).
    if message.query_type == "post_sales_checkin" and not message.booking_ref:
        score -= 0.10

    # ── Penalty 2: No property_id provided ───────────────────────────────────
    # Without a property_id, the AI has no specific data to draw from.
    # It falls back to generic Nistula brand context, which is less accurate.
    if not message.property_id:
        score -= 0.05

    # ── Penalty 3: Very short reply (< 50 characters) ────────────────────────
    # A reply this short likely means something went wrong (API error, empty response).
    # A real guest reply is almost always longer than 50 characters.
    if len(reply) < 50:
        score -= 0.15

    # ── Penalty 4: Reply contains uncertainty phrases ─────────────────────────
    # If Claude says "I don't know" or "I'm not sure", the reply is not trustworthy.
    # These phrases indicate Claude lacked the information to answer properly.
    lowered_reply = reply.lower()
    uncertainty_phrases = ["i don't know", "not sure", "i'm not certain", "i cannot"]
    if any(phrase in lowered_reply for phrase in uncertainty_phrases):
        score -= 0.20

    # Clamp to [0.0, 1.0] and round to 2 decimal places for clean output
    return round(max(0.0, min(1.0, score)), 2)


async def get_ai_reply(message: NormalisedMessage) -> tuple[str, float]:
    """
    Main entry point: get a drafted reply from Claude and compute its confidence score.

    Steps:
      1. Check if MOCK_AI mode is enabled (for testing without a real API key).
      2. Validate that ANTHROPIC_API_KEY is set in the environment.
      3. Fetch property context for the given property_id.
      4. Build the system prompt with property context and tone guidelines.
      5. Call the Claude API with the guest's message as the user prompt.
      6. Extract the reply text and compute the confidence score.
      7. Return both as a tuple.

    Args:
        message (NormalisedMessage): The normalised, classified guest message.

    Returns:
        tuple[str, float]: (drafted_reply_text, confidence_score)
          - drafted_reply_text: The Claude-generated guest-facing reply.
          - confidence_score: A float between 0.0 and 1.0.

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set in environment variables.
    """
    # ── MOCK MODE: Used by the pytest test suite ──────────────────────────────
    # Set MOCK_AI=true in .env to skip the real Claude API call.
    # This makes tests fast, free, and independent of API key availability.
    if os.getenv("MOCK_AI", "false").lower() == "true":
        mock_reply = _mock_reply(message)
        mock_confidence = _compute_confidence(message, "mock reply text that is long enough")
        return mock_reply, mock_confidence

    # ── API KEY CHECK ─────────────────────────────────────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not set in environment variables. "
            "Add it to your .env file: ANTHROPIC_API_KEY=sk-ant-..."
        )

    # ── PROPERTY CONTEXT ──────────────────────────────────────────────────────
    # Fetch property-specific data to include in the prompt.
    # Falls back to generic Nistula description if property_id is missing/unknown.
    property_context = get_property_context(message.property_id)

    # ── SYSTEM PROMPT ─────────────────────────────────────────────────────────
    # Builds the detailed instructions for Claude (persona, context, tone, rules).
    system_prompt = _build_system_prompt(message, property_context)

    # ── CLAUDE API CALL ───────────────────────────────────────────────────────
    # We use the synchronous Anthropic client wrapped in an async function
    # because FastAPI expects async route handlers for concurrent request handling.
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",  # The Claude model to use
        max_tokens=512,                    # Limit reply length (keeps responses concise)
        system=system_prompt,              # Instructions for Claude's behaviour
        messages=[
            {
                "role": "user",
                "content": message.message_text,  # The actual guest message
            }
        ],
    )

    # Extract the text content from the first response block
    reply_text = response.content[0].text.strip()

    # Compute our deterministic confidence score based on the reply and context
    confidence = _compute_confidence(message, reply_text)

    return reply_text, confidence


def _mock_reply(message: NormalisedMessage) -> str:
    """
    Returns a deterministic mock reply based on query type.

    Used ONLY when MOCK_AI=true (e.g., during pytest test runs).
    This avoids real API calls during testing, keeping tests fast and free.

    Each mock reply is realistic enough to test the full pipeline:
      - Classification check (does the right query_type get the right reply?)
      - Confidence scoring (is the reply long enough? Does it contain uncertainty phrases?)
      - Action routing (does a complaint still escalate even with a confident-sounding reply?)

    Args:
        message (NormalisedMessage): Used to extract first name and query type.

    Returns:
        str: A pre-written mock reply for the given query type.
    """
    # Extract first name from full name for a personalised greeting
    first_name = message.guest_name.split()[0]

    replies = {
        "pre_sales_availability": (
            f"Hi {first_name}! Great news — Villa B1 is available from April 20 to 24. "
            f"We'd love to host you! The villa features 3 bedrooms, a private pool, and is nestled in Assagao, North Goa. "
            f"Shall I go ahead and reserve these dates for you?"
        ),
        "pre_sales_pricing": (
            f"Hi {first_name}! Our base rate at Villa B1 is INR 18,000 per night for up to 4 guests. "
            f"For 2 adults over 4 nights, that would be INR 72,000 in total. "
            f"Check-in is at 2pm and check-out at 11am. Would you like to proceed with a booking?"
        ),
        "post_sales_checkin": (
            f"Hi {first_name}, we're so excited to welcome you! Check-in is from 2:00 PM and check-out by 11:00 AM. "
            f"The WiFi password is Nistula@2024. Our caretaker is available 8am–10pm for anything you need. "
            f"Is there anything else I can help you with before your arrival?"
        ),
        "special_request": (
            f"Hi {first_name}! Absolutely, we'd love to arrange that for you. "
            f"Could you share a few more details so we can confirm availability and coordinate with our team? "
            f"We'll make sure everything is perfect for your stay."
        ),
        "complaint": (
            f"Hi {first_name}, I'm so sorry — this is completely unacceptable, and I genuinely apologise for the inconvenience. "
            f"I'm escalating this right now to our caretaker and on-call team. "
            f"Someone will reach out to you within 15 minutes. We will make this right."
        ),
        "general_enquiry": (
            f"Hi {first_name}! Happy to help. Villa B1 in Assagao, North Goa has 3 bedrooms, a private pool, "
            f"and can accommodate up to 6 guests. Our caretaker is on-site 8am–10pm. "
            f"Feel free to ask anything else!"
        ),
    }

    # Return the matching mock reply, or a generic fallback if the type is somehow unknown
    return replies.get(
        message.query_type,
        f"Hi {first_name}, thank you for reaching out! We'll get back to you shortly."
    )
