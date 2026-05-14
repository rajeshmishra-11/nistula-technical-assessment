"""
property_context.py — Mock Property Data Store
===============================================

This module provides property-specific context that is injected into the
Claude AI system prompt so the AI can give SPECIFIC, grounded answers
instead of generic ones.

EXAMPLE WITHOUT property context:
  Guest: "What's the wifi password?"
  AI: "Please contact the property for wifi details." ← useless

EXAMPLE WITH property context:
  Guest: "What's the wifi password?"
  AI: "Hi Sneha! The WiFi password is Nistula@2024." ← actually helpful

HOW IT WORKS:
  - PROPERTY_CONTEXT is a dictionary keyed by property_id (e.g., "villa-b1").
  - When a message comes in with a property_id, get_property_context() looks it up
    and returns a formatted string with all the property details.
  - This string is embedded into the AI system prompt in ai_service.py.
  - If the property_id is missing or unknown, it falls back to a generic
    Nistula brand description so Claude still has some context to work with.

IN PRODUCTION:
  This would be replaced with a database query:
    property = db.query(Property).filter(Property.code == property_id).first()
  The schema for this table is defined in schema.sql.

TO ADD A NEW PROPERTY:
  Add a new key-value pair to PROPERTY_CONTEXT below.
  The key must match the property_id that callers send in their webhook payload.
"""

# ─────────────────────────────────────────────────────────────
# Property Data Store (mock — static dict for this assessment)
# ─────────────────────────────────────────────────────────────
# In production: fetched from the `properties` table in PostgreSQL.

PROPERTY_CONTEXT: dict[str, dict] = {
    "villa-b1": {
        "name": "Villa B1",
        "location": "Assagao, North Goa",
        "bedrooms": 3,
        "max_guests": 6,
        "private_pool": True,
        "check_in": "2:00 PM",
        "check_out": "11:00 AM",
        "base_rate": "INR 18,000 per night (up to 4 guests)",
        "extra_guest_rate": "INR 2,000 per night per additional person",
        "wifi_password": "Nistula@2024",
        "caretaker": "Available 8am to 10pm",
        "chef_on_call": "Yes, pre-booking required",
        "availability_april_20_24": "Available",
        "cancellation_policy": "Free cancellation up to 7 days before check-in",
    }
    # Add more properties here as needed:
    # "villa-c2": { "name": "Villa C2", ... }
}


def get_property_context(property_id: str | None) -> str:
    """
    Returns a formatted property context string for use in AI system prompts.

    If the property_id is known, returns detailed property info so the AI
    can give specific, accurate answers.

    If the property_id is None or not found in our store, returns a generic
    Nistula brand description as a fallback so the AI still has some context.

    Args:
        property_id (str | None): The property identifier from the inbound message.
                                  Example: "villa-b1". Can be None.

    Returns:
        str: A multi-line string with property details, ready to embed in a prompt.

    Examples:
        get_property_context("villa-b1")
        → "Property: Villa B1, Assagao, North Goa\\nBedrooms: 3 | ..."

        get_property_context(None)
        → "Nistula is a luxury villa hospitality company in Goa, India. ..."

        get_property_context("unknown-villa")
        → "Nistula is a luxury villa hospitality company in Goa, India. ..."
    """
    if property_id and property_id in PROPERTY_CONTEXT:
        # Property found — build a detailed, structured context string
        p = PROPERTY_CONTEXT[property_id]
        return (
            f"Property: {p['name']}, {p['location']}\n"
            f"Bedrooms: {p['bedrooms']} | Max guests: {p['max_guests']} | "
            f"Private pool: {'Yes' if p['private_pool'] else 'No'}\n"
            f"Check-in: {p['check_in']} | Check-out: {p['check_out']}\n"
            f"Base rate: {p['base_rate']}\n"
            f"Extra guest charge: {p['extra_guest_rate']}\n"
            f"WiFi password: {p['wifi_password']}\n"
            f"Caretaker: {p['caretaker']}\n"
            f"Chef on call: {p['chef_on_call']}\n"
            f"Availability April 20–24: {p['availability_april_20_24']}\n"
            f"Cancellation policy: {p['cancellation_policy']}"
        )

    # Fallback: property not found or not provided — use brand-level context
    # This ensures the AI still sounds like a Nistula representative, not a generic bot.
    return (
        "Nistula is a luxury villa hospitality company in Goa, India. "
        "We manage multiple high-end properties with private pools, caretakers, and personalised services. "
        "If you need specific property details, please refer the guest to our team."
    )
