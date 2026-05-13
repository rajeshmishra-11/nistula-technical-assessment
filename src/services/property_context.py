"""
Property context store.
In production this would be fetched from a database.
For this assessment, we use a static mock store keyed by property_id.
"""

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
        "extra_guest_rate": "INR 2,000 per night per person",
        "wifi_password": "Nistula@2024",
        "caretaker": "Available 8am to 10pm",
        "chef_on_call": "Yes, pre-booking required",
        "availability_april_20_24": "Available",
        "cancellation_policy": "Free cancellation up to 7 days before check-in",
    }
}


def get_property_context(property_id: str | None) -> str:
    """
    Returns a formatted property context string for use in AI prompts.
    Falls back to a generic Nistula description if property not found.
    """
    if property_id and property_id in PROPERTY_CONTEXT:
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
    return (
        "Nistula is a luxury villa hospitality company in Goa, India. "
        "We manage multiple high-end properties with private pools, caretakers, and personalised services."
    )
