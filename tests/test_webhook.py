"""
Integration tests for the /webhook/message endpoint.
Tests 3+ different input scenarios as required by the assessment.
Run with: pytest tests/ -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

# We patch the AI service so tests run without a real API key
MOCK_REPLY = "Hi Rahul! Great news — Villa B1 is available from April 20 to 24."
MOCK_CONFIDENCE = 0.92


@pytest.fixture
def client():
    """Create a test client with AI service mocked."""
    with patch("src.services.ai_service.get_ai_reply", new_callable=AsyncMock) as mock_ai:
        mock_ai.return_value = (MOCK_REPLY, MOCK_CONFIDENCE)
        from src.main import app
        with TestClient(app) as c:
            yield c


# ─────────────────────────────────────────────
# Test 1: Pre-sales availability query
# ─────────────────────────────────────────────

def test_availability_query(client):
    """Standard availability + pricing query via WhatsApp."""
    payload = {
        "source": "whatsapp",
        "guest_name": "Rahul Sharma",
        "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
        "timestamp": "2026-05-05T10:30:00Z",
        "booking_ref": "NIS-2024-0891",
        "property_id": "villa-b1",
    }
    response = client.post("/webhook/message", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query_type"] == "pre_sales_availability"
    assert "message_id" in data
    assert data["confidence_score"] == MOCK_CONFIDENCE
    assert data["action"] == "auto_send"  # confidence 0.92 >= 0.85
    assert len(data["drafted_reply"]) > 0


# ─────────────────────────────────────────────
# Test 2: Complaint query — must escalate
# ─────────────────────────────────────────────

def test_complaint_always_escalates(client):
    """Complaints must always be escalated regardless of confidence."""
    payload = {
        "source": "whatsapp",
        "guest_name": "Priya Mehta",
        "message": "There is no hot water and the AC is not working. This is unacceptable. I want a refund.",
        "timestamp": "2026-05-06T03:00:00Z",
        "booking_ref": "NIS-2024-1234",
        "property_id": "villa-b1",
    }
    response = client.post("/webhook/message", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query_type"] == "complaint"
    assert data["action"] == "escalate"  # complaints always escalate


# ─────────────────────────────────────────────
# Test 3: Post-sales check-in query
# ─────────────────────────────────────────────

def test_checkin_query(client):
    """Check-in info query from a confirmed booking guest."""
    payload = {
        "source": "direct",
        "guest_name": "Ananya Singh",
        "message": "Hi, what time can we check in and what's the WiFi password?",
        "timestamp": "2026-05-07T09:00:00Z",
        "booking_ref": "NIS-2024-5678",
        "property_id": "villa-b1",
    }
    response = client.post("/webhook/message", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query_type"] == "post_sales_checkin"
    assert data["action"] in ("auto_send", "agent_review", "escalate")


# ─────────────────────────────────────────────
# Test 4: Special request via Airbnb
# ─────────────────────────────────────────────

def test_special_request(client):
    """Airport transfer special request from Airbnb."""
    payload = {
        "source": "airbnb",
        "guest_name": "James O'Brien",
        "message": "Can you arrange an airport transfer from Goa Airport on April 20 at 2pm for 3 people?",
        "timestamp": "2026-05-08T14:00:00Z",
        "booking_ref": None,
        "property_id": "villa-b1",
    }
    response = client.post("/webhook/message", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query_type"] == "special_request"


# ─────────────────────────────────────────────
# Test 5: General enquiry — pets
# ─────────────────────────────────────────────

def test_general_enquiry(client):
    """Pet policy general enquiry from Instagram."""
    payload = {
        "source": "instagram",
        "guest_name": "Meera Kapoor",
        "message": "Do you allow pets at the villa? We have a small dog.",
        "timestamp": "2026-05-09T11:30:00Z",
        "booking_ref": None,
        "property_id": "villa-b1",
    }
    response = client.post("/webhook/message", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["query_type"] == "general_enquiry"


# ─────────────────────────────────────────────
# Test 6: Invalid source channel — should fail validation
# ─────────────────────────────────────────────

def test_invalid_source_rejected(client):
    """An unrecognised source channel should be rejected by Pydantic."""
    payload = {
        "source": "telegram",  # not in allowed list
        "guest_name": "Test User",
        "message": "Hello",
        "timestamp": "2026-05-09T11:00:00Z",
    }
    response = client.post("/webhook/message", json=payload)
    assert response.status_code == 422  # Unprocessable Entity


# ─────────────────────────────────────────────
# Test 7: Health check
# ─────────────────────────────────────────────

def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
