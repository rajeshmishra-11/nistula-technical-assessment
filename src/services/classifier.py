"""
classifier.py — Rule-Based Query Classifier
============================================

This module classifies a guest's raw message text into one of six query types.

HOW IT WORKS:
  - We define a list of rules (_RULES), where each rule is a pair of:
      (list of regex patterns, query_type_label)
  - The rules are checked IN ORDER (highest priority first).
  - The FIRST rule whose ANY pattern matches the message wins.
  - If NO rule matches at all, we fall back to "general_enquiry".

WHY RULE-BASED (not asking Claude to classify)?
  - Speed: No extra API call = lower latency for the guest.
  - Cost: Every Claude API call costs tokens. Classification would double the cost.
  - Determinism: Rules are predictable and testable. Claude's classification can vary.
  - Transparency: Any developer can read the rules and know exactly why a message
    was classified a certain way. Easy to debug, easy to extend.

HOW TO ADD A NEW QUERY TYPE:
  1. Add the new type to QueryType in schemas.py.
  2. Add a new tuple to _RULES with patterns and the new label.
  3. Place it in the correct priority position (complaints must stay first).
"""

import re
from src.models.schemas import QueryType


# ─────────────────────────────────────────────────────────────
# Classification Rules
# ─────────────────────────────────────────────────────────────
# Each entry is: (list_of_regex_patterns, query_type_label)
#
# PRIORITY ORDER MATTERS:
#   - Complaints are first because a message like
#     "No hot water — I want a refund AND what are your dates?"
#     should be treated as a complaint, not an availability query.
#   - post_sales_checkin before pre_sales so "check-in time" (post-sales)
#     is not confused with general booking questions.
#   - general_enquiry is LAST — it's the catch-all bucket.
#
# Pattern notes:
#   r"check.?in" matches "check-in", "checkin", "check in" (the .? means optional char)
#   r"\bRS\b"    matches "RS" as a whole word (not inside "FIRST" etc.)
#   r"april\\s+\\d+" matches "april 20", "april 24", etc.

_RULES: list[tuple[list[str], QueryType]] = [

    # ── 1. COMPLAINT ─────────────────────────────────────────
    # Checked first because complaints override everything else.
    # A complaint must ALWAYS be escalated to a human — no exceptions.
    (
        [
            r"not\s+happy",        # "I'm not happy with..."
            r"unacceptable",       # "This is unacceptable"
            r"refund",             # "I want a refund"
            r"complaint",          # "I have a complaint"
            r"broken",             # "The AC is broken"
            r"not\s+working",      # "The geyser is not working"
            r"terrible",           # "Terrible experience"
            r"worst",              # "Worst stay ever"
            r"horrible",           # "Horrible property"
            r"no\s+hot\s+water",   # "There is no hot water"
            r"ac\s+not",           # "AC not working"
            r"disgusting",         # "The place was disgusting"
            r"outraged",           # "I am outraged"
            r"furious",            # "We are furious"
            r"demand\s+refund",    # "I demand a refund"
        ],
        "complaint",
    ),

    # ── 2. POST-SALES CHECK-IN INFO ──────────────────────────
    # Guest has already booked and wants practical arrival/stay info.
    # Key signals: wifi, password, check-in time, key, directions.
    (
        [
            r"check.?in\s+time",   # "What is the check-in time?"
            r"check.?out\s+time",  # "What time is checkout?"
            r"wifi",               # "What's the wifi?"
            r"wi.fi",              # "Wi-Fi password?"
            r"password",           # "What's the password?"
            r"directions",         # "How do I get there?"
            r"how\s+do\s+i\s+get", # "How do I get to the villa?"
            r"access\s+code",      # "What is the access code?"
            r"key",                # "Where do I pick up the key?"
            r"caretaker",          # "Who is the caretaker?"
            r"arrival",            # "What should I do on arrival?"
        ],
        "post_sales_checkin",
    ),

    # ── 3. SPECIAL REQUEST ───────────────────────────────────
    # Guest wants something extra arranged — transfers, celebrations, etc.
    # These often need human confirmation so confidence is lower (0.78 base).
    (
        [
            r"early\s+check.?in",      # "Can we do early check-in?"
            r"late\s+check.?out",      # "Can we check out late?"
            r"airport\s+transfer",     # "Need an airport transfer"
            r"pickup",                 # "Can you arrange a pickup?"
            r"drop.?off",              # "Drop-off at airport?"
            r"birthday",               # "It's my wife's birthday"
            r"anniversary",            # "Our anniversary trip"
            r"chef",                   # "We'd like a private chef"
            r"special\s+arrangement",  # "Can you make a special arrangement?"
            r"decoration",             # "Room decoration please"
        ],
        "special_request",
    ),

    # ── 4. PRE-SALES AVAILABILITY ────────────────────────────
    # Guest is checking if the property is free on certain dates.
    # Has NOT booked yet. Signals: dates, "available", "book".
    (
        [
            r"available",      # "Is the villa available?"
            r"availability",   # "What is your availability?"
            r"free\s+on",      # "Are you free on..."
            r"open\s+on",      # "Are you open on..."
            r"april\s+\d+",    # "April 20", "April 5", etc.
            r"may\s+\d+",      # "May 14", etc.
            r"june\s+\d+",
            r"july\s+\d+",
            r"august\s+\d+",
            r"dates?",         # "What dates are free?" / "These dates?"
            r"book",           # "Can I book?"
            r"booking",        # "I'm interested in booking"
        ],
        "pre_sales_availability",
    ),

    # ── 5. PRE-SALES PRICING ─────────────────────────────────
    # Guest is asking about price before committing to a booking.
    # Signals: rate, price, cost, how much, INR, rupee.
    (
        [
            r"rate",           # "What is your rate?"
            r"price",          # "What is the price?"
            r"cost",           # "What does it cost?"
            r"how\s+much",     # "How much per night?"
            r"charge",         # "What do you charge?"
            r"fee",            # "Are there any fees?"
            r"per\s+night",    # "Per night cost?"
            r"tariff",         # "What is your tariff?"
            r"INR",            # "Is it INR 10,000?"
            r"\bRS\b",         # "RS 15,000?" (as a whole word)
            r"rupee",          # "How many rupees?"
        ],
        "pre_sales_pricing",
    ),

    # ── 6. GENERAL ENQUIRY (catch-all) ───────────────────────
    # Anything that didn't match the above categories.
    # Also explicitly catches common amenity/facility questions.
    (
        [
            r"pet",            # "Do you allow pets?"
            r"parking",        # "Is there parking?"
            r"pool",           # "Does it have a pool?"
            r"kitchen",        # "Is there a kitchen?"
            r"breakfast",      # "Is breakfast included?"
            r"food",           # "Can we arrange food?"
            r"nearby",         # "What's nearby?"
            r"restaurant",     # "Are there restaurants near?"
            r"beach",          # "How far is the beach?"
            r"amenities",      # "What are the amenities?"
        ],
        "general_enquiry",
    ),
]


def classify_query(message: str) -> QueryType:
    """
    Classify a guest message into one of the defined QueryType categories.

    Algorithm:
      1. Lowercase the message (all patterns are lowercase).
      2. Loop through _RULES in priority order.
      3. For each rule, check all regex patterns against the message.
      4. Return the query_type of the FIRST rule that gets ANY match.
      5. If nothing matches, return "general_enquiry" as the safe default.

    Args:
        message (str): The raw guest message text (e.g., "What is the wifi password?")

    Returns:
        QueryType: One of the six classification labels.

    Examples:
        classify_query("Is the villa available in April?")  → "pre_sales_availability"
        classify_query("This is unacceptable, I want a refund") → "complaint"
        classify_query("Hello, can I bring my dog?")        → "general_enquiry"
    """
    lowered = message.lower()  # Normalise to lowercase so patterns don't need to handle case

    for patterns, query_type in _RULES:
        for pattern in patterns:
            if re.search(pattern, lowered):
                # First match wins — return immediately without checking remaining rules
                return query_type

    # No rule matched — default to general_enquiry (safe, human-readable fallback)
    return "general_enquiry"
