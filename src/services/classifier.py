"""
Query classifier.
Uses keyword/pattern matching for fast, deterministic classification.
Falls back gracefully if no pattern matches.
"""

import re
from src.models.schemas import QueryType


# ─────────────────────────────────────────────
# Classification Rules (ordered by priority)
# ─────────────────────────────────────────────

_RULES: list[tuple[list[str], QueryType]] = [
    # Complaints come first — highest priority (always escalate)
    (
        [
            r"not\s+happy", r"unacceptable", r"refund", r"complaint",
            r"broken", r"not\s+working", r"terrible", r"worst", r"horrible",
            r"no\s+hot\s+water", r"ac\s+not", r"disgusting", r"outraged",
            r"furious", r"demand\s+refund",
        ],
        "complaint",
    ),
    # Post-sales check-in information
    (
        [
            r"check.?in\s+time", r"check.?out\s+time", r"wifi", r"wi.fi",
            r"password", r"directions", r"how\s+do\s+i\s+get", r"access\s+code",
            r"key", r"caretaker", r"arrival",
        ],
        "post_sales_checkin",
    ),
    # Special requests
    (
        [
            r"early\s+check.?in", r"late\s+check.?out", r"airport\s+transfer",
            r"pickup", r"drop.?off", r"birthday", r"anniversary", r"chef",
            r"special\s+arrangement", r"decoration",
        ],
        "special_request",
    ),
    # Pre-sales availability
    (
        [
            r"available", r"availability", r"free\s+on", r"open\s+on",
            r"april\s+\d+", r"may\s+\d+", r"june\s+\d+", r"july\s+\d+",
            r"august\s+\d+", r"dates?", r"book", r"booking",
        ],
        "pre_sales_availability",
    ),
    # Pre-sales pricing
    (
        [
            r"rate", r"price", r"cost", r"how\s+much", r"charge",
            r"fee", r"per\s+night", r"tariff", r"INR", r"\bRS\b", r"rupee",
        ],
        "pre_sales_pricing",
    ),
    # General enquiry — catch-all
    (
        [
            r"pet", r"parking", r"pool", r"kitchen", r"breakfast",
            r"food", r"nearby", r"restaurant", r"beach", r"amenities",
        ],
        "general_enquiry",
    ),
]


def classify_query(message: str) -> QueryType:
    """
    Classify a guest message into one of the defined query types.

    Strategy:
    - Iterate rules in priority order.
    - Return the first matching query type.
    - Default to 'general_enquiry' if nothing matches.
    """
    lowered = message.lower()
    for patterns, query_type in _RULES:
        for pattern in patterns:
            if re.search(pattern, lowered):
                return query_type
    # Fallback
    return "general_enquiry"
