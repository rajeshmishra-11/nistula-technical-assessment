# Part 3 — Thinking Question

## Scenario

> It is 3am. A guest at Villa B1 sends a WhatsApp message:
> "There is no hot water and we have guests arriving for breakfast in 4 hours.
> This is unacceptable. I want a refund for tonight."

---

## Question A — The Immediate Response

**The actual AI message:**

> Hi [Guest Name], I'm so sorry — this is completely unacceptable, and I understand how stressful this is, especially with guests arriving in just a few hours.
>
> I'm escalating this right now to our caretaker and the Nistula on-call team. Someone will contact you within 15 minutes to fix the hot water issue tonight. You have my word.
>
> Regarding the refund — you absolutely deserve a resolution, and our team will discuss this with you first thing. Please don't worry; we will make this right.

**Why this wording:**

The reply leads with a genuine apology before anything else — guests in distress need to feel heard, not managed. It commits to a *specific timeframe* (15 minutes) rather than vague promises, which reduces anxiety and sets a clear expectation. The refund request is neither dismissed nor confirmed on the spot (which could create a liability), but is acknowledged warmly with a commitment to follow up — keeping the human agent in control of that decision.

---

## Question B — The System Design

Beyond sending the message, the platform should trigger a multi-layered response:

1. **Immediate escalation flag**: The message is classified as `complaint` and `confidence_score` drops below 0.50 → `action = escalate`. The system bypasses auto-send entirely.

2. **Push notification to on-call staff**: The platform fires an alert (SMS + app push) to the property caretaker and the Nistula duty manager simultaneously, with the full message text, guest name, property, and booking reference. The caretaker is instructed to call the guest directly within 15 minutes.

3. **Incident record created**: A structured incident log is opened in the system, linking the message to the guest, property, booking reference, and timestamp. This is separate from the conversation log so it can be tracked through resolution.

4. **Reservation flagged**: The reservation record is updated with a `has_open_incident = true` flag, preventing any automated marketing or check-out messages from going out until the incident is resolved.

5. **Logging**: The full AI-drafted reply, the final sent reply, the confidence score, the escalation trigger, and all staff notification timestamps are written to the database.

6. **30-minute no-response protocol**: If no human agent has marked the incident as "acknowledged" within 30 minutes, the platform sends a second escalation — this time to the Nistula founder/senior on-call — and sends the guest a follow-up message:
   > "Hi [Name], I want to confirm our team is actively working on this. You will hear from us very shortly."

This prevents the guest from feeling abandoned at 3am and gives Nistula a safety net against human oversight failures.

---

## Question C — The Learning

When the same failure pattern appears three or more times, the system should stop just reacting and start preventing.

**What the system should detect:**
A recurring-complaint detector runs on the incident log. When the same `property_id` accumulates 3+ incidents with a similar complaint keyword (e.g., "hot water", "geyser", "no hot water") within a rolling 60-day window, it automatically raises a **property issue alert** — a structured ticket sent to the property operations team.

**What I would build to prevent a fourth complaint:**

1. **Post-stay maintenance trigger**: After each hot-water complaint, a maintenance checklist is automatically created and assigned to the caretaker: inspect the geyser, test water temperature, log status. Completion is tracked in the platform.

2. **Pre-arrival proactive check**: The platform adds a "hot water check" task to the pre-arrival checklist for Villa B1. This runs 24 hours before every check-in and requires caretaker sign-off before the task is closed.

3. **Vendor escalation**: If the issue persists across 3 stays, the platform generates a report for the property manager showing the pattern, recommending geyser replacement or a plumber inspection — with guest satisfaction cost (refunds + potential lost reviews) quantified alongside repair costs.

4. **Guest recovery**: The platform flags the two previously affected guests and prompts the team to send a goodwill gesture (a discount code, a personalised note) — because a third complaint means the first two probably left quietly unhappy.

The principle: the system should never treat a complaint as a closed event. Every resolved complaint is a data point, and three data points are a pattern that demands a structural response.

---
