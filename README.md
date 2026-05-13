# Nistula Guest Message Handler
**Nistula Summer 2026 Technical Assessment — Rajesh Kumar Mishra**

---

## Overview

A FastAPI backend that receives inbound guest messages via webhook, normalises them into a unified schema, classifies the query type, generates an AI-drafted reply using the Claude API, and returns the reply with a confidence score and recommended action.

---

## Project Structure

```
nistula-technical-assessment/
├── src/
│   ├── main.py                     # FastAPI app entry point
│   ├── routes/
│   │   └── webhook.py              # POST /webhook/message handler
│   ├── models/
│   │   └── schemas.py              # Pydantic request/response models
│   └── services/
│       ├── classifier.py           # Rule-based query classifier
│       ├── property_context.py     # Mock property data store
│       └── ai_service.py           # Claude API integration + confidence scoring
├── tests/
│   └── test_webhook.py             # 7 integration tests
├── schema.sql                      # Part 2: PostgreSQL schema
├── thinking.md                     # Part 3: Written answers
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup Instructions

### 1. Clone the repository

```bash
git clone https://github.com/rajeshmishra-11/nistula-technical-assessment.git
cd nistula-technical-assessment
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env and add your Anthropic API key:
# ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Run the server

```bash
uvicorn src.main:app --reload
```

The API will be available at: `http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

### 5. Run tests

```bash
python -m pytest tests/ -v
```

---

## API Usage

### `POST /webhook/message`

**Request body:**

```json
{
  "source": "whatsapp",
  "guest_name": "Rahul Sharma",
  "message": "Is the villa available from April 20 to 24? What is the rate for 2 adults?",
  "timestamp": "2026-05-05T10:30:00Z",
  "booking_ref": "NIS-2024-0891",
  "property_id": "villa-b1"
}
```

Accepted values for `source`: `whatsapp`, `booking_com`, `airbnb`, `instagram`, `direct`

**Response:**

```json
{
  "message_id": "3f2a91b0-...",
  "query_type": "pre_sales_availability",
  "drafted_reply": "Hi Rahul! Great news — Villa B1 is available from April 20 to 24...",
  "confidence_score": 0.92,
  "action": "auto_send"
}
```

---

## Confidence Scoring Logic

The confidence score (0.0 – 1.0) is computed deterministically after the AI generates a reply. It is **not** derived from Claude's internal state — it is a measure of how much context the system had available and how unambiguous the query was.

### Base scores by query type

| Query Type | Base Score | Reasoning |
|---|---|---|
| `pre_sales_availability` | 0.92 | Availability is factual; answer is clear-cut |
| `pre_sales_pricing` | 0.90 | Rate info is fully in property context |
| `post_sales_checkin` | 0.88 | Check-in details are precise and known |
| `special_request` | 0.78 | May need clarification or human judgment |
| `general_enquiry` | 0.75 | Variable scope; answer may be incomplete |
| `complaint` | 0.45 | Always requires human empathy and judgment |

### Penalties applied

| Condition | Penalty |
|---|---|
| Post-sales query without a booking reference | −0.10 |
| No `property_id` provided (can't ground context) | −0.05 |
| AI reply is < 50 characters (likely failed) | −0.15 |
| Reply contains uncertainty phrases ("I don't know", "not sure") | −0.20 |

### Action thresholds

| Score range | Action |
|---|---|
| ≥ 0.85 | `auto_send` — send directly to guest |
| 0.60 – 0.84 | `agent_review` — human reviews before sending |
| < 0.60 | `escalate` — flag for human handling |
| Any `complaint` | `escalate` — always, regardless of score |

---

## Query Classification

Classification uses a priority-ordered rule engine with regex patterns:

1. **`complaint`** — checked first (overrides all others)
2. **`post_sales_checkin`** — WiFi, passwords, check-in times
3. **`special_request`** — airport transfers, early check-in
4. **`pre_sales_availability`** — date availability, booking enquiries
5. **`pre_sales_pricing`** — rates, costs, per-night pricing
6. **`general_enquiry`** — pets, parking, amenities (catch-all)

This ordering ensures that a message mentioning both availability and a complaint is correctly classified as a complaint.

---

## Design Decisions

**Why FastAPI?** Async support, automatic OpenAPI docs, and Pydantic validation make it ideal for a webhook handler that needs to handle concurrent requests and expose clear API contracts.

**Why rule-based classification instead of asking Claude?** Speed, cost, and determinism. Sending a second API call just to classify would double latency and cost. The regex rules are readable, testable, and maintainable. If a new query type is needed, adding a pattern takes one line.

**Why not store messages in the webhook handler?** Out of scope for this assessment, but the schema in `schema.sql` fully supports it. The webhook handler is stateless — persistence would be added by calling a repository layer after the AI response.

---

## Part 2 & Part 3

- **Database schema:** See [`schema.sql`](./schema.sql)
- **Thinking answers:** See [`thinking.md`](./thinking.md)
