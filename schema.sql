-- ============================================================
-- Nistula Unified Messaging Platform - PostgreSQL Schema
-- ============================================================
-- Design principles:
--   1. One guest record across all channels (deduplicated by phone/email)
--   2. All messages in a single messages table (channel-agnostic)
--   3. Conversations link guests to reservations
--   4. Full AI audit trail: draft → edit → send tracking
--   5. AI confidence score and query type stored per inbound message
-- ============================================================


-- ─────────────────────────────────────────────────────────────
-- ENUM TYPES
-- ─────────────────────────────────────────────────────────────

CREATE TYPE source_channel AS ENUM (
    'whatsapp',
    'booking_com',
    'airbnb',
    'instagram',
    'direct'
);

CREATE TYPE query_type AS ENUM (
    'pre_sales_availability',
    'pre_sales_pricing',
    'post_sales_checkin',
    'special_request',
    'complaint',
    'general_enquiry'
);

-- How a message was handled (AI pipeline audit)
CREATE TYPE message_handling_status AS ENUM (
    'ai_drafted',       -- AI generated a draft, not yet sent
    'agent_edited',     -- A human agent edited the AI draft before sending
    'auto_sent',        -- AI draft was sent automatically (high confidence)
    'agent_sent',       -- A human agent wrote and sent the reply directly
    'escalated',        -- Flagged for escalation; no reply sent yet
    'no_reply_needed'   -- Message did not require a reply
);

CREATE TYPE action_type AS ENUM (
    'auto_send',
    'agent_review',
    'escalate'
);

CREATE TYPE reservation_status AS ENUM (
    'enquiry',
    'confirmed',
    'checked_in',
    'checked_out',
    'cancelled'
);


-- ─────────────────────────────────────────────────────────────
-- 1. PROPERTIES
-- Master list of villas / properties managed by Nistula.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_code   VARCHAR(50) UNIQUE NOT NULL,   -- e.g. 'villa-b1'
    name            VARCHAR(255) NOT NULL,
    location        VARCHAR(255),
    bedrooms        SMALLINT,
    max_guests      SMALLINT,
    base_rate_inr   NUMERIC(10, 2),                -- per night up to base occupancy
    extra_guest_inr NUMERIC(10, 2),                -- per additional guest per night
    check_in_time   TIME DEFAULT '14:00:00',
    check_out_time  TIME DEFAULT '11:00:00',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────
-- 2. GUESTS
-- One record per unique guest, regardless of channel.
--
-- DESIGN DECISION: Guest deduplication is the hardest problem here.
-- A guest may book on Airbnb as "Rahul S" and WhatsApp as "Rahul Sharma".
-- We store the canonical identity here and link channel-specific identifiers
-- in guest_channel_identities. Phone number is the primary dedup key
-- (most reliable across channels in India). Email is secondary.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE guests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(320) UNIQUE,            -- nullable; guest may not share email
    phone           VARCHAR(20) UNIQUE,             -- primary dedup key (E.164 format)
    nationality     VARCHAR(100),
    notes           TEXT,                           -- internal notes about the guest
    is_vip          BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Store per-channel external identifiers for the same guest.
-- Allows us to match "Rahul on WhatsApp" to "Rahul on Airbnb".
CREATE TABLE guest_channel_identities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id        UUID NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    channel         source_channel NOT NULL,
    external_id     VARCHAR(500) NOT NULL,          -- WhatsApp number, Airbnb guest ID, etc.
    display_name    VARCHAR(255),                   -- name as shown on that channel
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (channel, external_id)                   -- one external ID per channel
);


-- ─────────────────────────────────────────────────────────────
-- 3. RESERVATIONS
-- A reservation links a guest to a property for a date range.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE reservations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_ref     VARCHAR(100) UNIQUE NOT NULL,   -- e.g. 'NIS-2024-0891'
    guest_id        UUID NOT NULL REFERENCES guests(id),
    property_id     UUID NOT NULL REFERENCES properties(id),
    check_in_date   DATE NOT NULL,
    check_out_date  DATE NOT NULL,
    num_adults      SMALLINT NOT NULL DEFAULT 2,
    num_children    SMALLINT NOT NULL DEFAULT 0,
    total_amount_inr NUMERIC(12, 2),
    status          reservation_status DEFAULT 'enquiry',
    channel         source_channel NOT NULL,        -- which channel this booking came from
    channel_booking_id VARCHAR(255),                -- OTA-specific booking ID (e.g. Airbnb reservation #)
    special_requests TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT valid_dates CHECK (check_out_date > check_in_date)
);


-- ─────────────────────────────────────────────────────────────
-- 4. CONVERSATIONS
-- A conversation groups related messages (e.g., one thread per stay).
-- Linked to a guest; optionally linked to a reservation.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_id        UUID NOT NULL REFERENCES guests(id),
    reservation_id  UUID REFERENCES reservations(id),  -- NULL for pre-booking enquiries
    property_id     UUID REFERENCES properties(id),
    channel         source_channel NOT NULL,
    subject         VARCHAR(500),                   -- optional label/topic
    is_open         BOOLEAN DEFAULT TRUE,           -- FALSE when resolved
    escalated       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────
-- 5. MESSAGES
-- All messages across all channels in one table.
-- Stores both inbound (guest → Nistula) and outbound (Nistula → guest).
-- ─────────────────────────────────────────────────────────────

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    guest_id        UUID REFERENCES guests(id),
    reservation_id  UUID REFERENCES reservations(id),
    property_id     UUID REFERENCES properties(id),

    -- Channel info
    source          source_channel NOT NULL,
    direction       VARCHAR(10) NOT NULL CHECK (direction IN ('inbound', 'outbound')),

    -- Content
    message_text    TEXT NOT NULL,
    sent_at         TIMESTAMPTZ NOT NULL,           -- when the guest/system sent the message
    received_at     TIMESTAMPTZ DEFAULT NOW(),      -- when our system received it

    -- Classification (for inbound messages only)
    query_type      query_type,                     -- NULL for outbound
    
    -- AI pipeline fields (for inbound messages)
    ai_confidence_score     NUMERIC(4, 3),          -- 0.000 – 1.000
    ai_recommended_action   action_type,
    ai_drafted_reply        TEXT,                   -- what Claude drafted
    
    -- Handling audit (for the outbound reply to this message)
    handling_status         message_handling_status DEFAULT 'ai_drafted',
    agent_id                UUID,                   -- which agent edited/sent (if applicable)
    final_reply_text        TEXT,                   -- what was actually sent (may differ from ai_drafted_reply)
    replied_at              TIMESTAMPTZ,            -- when the reply was sent

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast conversation lookups
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_guest_id ON messages(guest_id);
CREATE INDEX idx_messages_sent_at ON messages(sent_at DESC);
CREATE INDEX idx_messages_query_type ON messages(query_type);
CREATE INDEX idx_messages_handling_status ON messages(handling_status);


-- ─────────────────────────────────────────────────────────────
-- 6. AI INTERACTION LOG
-- Immutable audit log of every Claude API call.
-- Separate from messages to keep messages table clean.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE ai_interaction_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id          UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    model_used          VARCHAR(100) NOT NULL,       -- e.g. 'claude-sonnet-4-20250514'
    system_prompt       TEXT,
    user_prompt         TEXT NOT NULL,
    raw_response        TEXT,
    confidence_score    NUMERIC(4, 3),
    tokens_used         INTEGER,
    latency_ms          INTEGER,
    error_message       TEXT,                        -- populated if API call failed
    created_at          TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────
-- DESIGN DECISIONS
-- ─────────────────────────────────────────────────────────────

-- Hardest decision: Guest identity across channels
-- -----------------------------------------------
-- The trickiest schema decision was how to handle the same real-world guest
-- appearing under different names/IDs across WhatsApp, Airbnb, and Booking.com.
-- I chose to separate the canonical guest identity (guests table) from
-- channel-specific identifiers (guest_channel_identities). This avoids data
-- duplication while enabling cross-channel matching. The deduplication logic
-- (merging "Rahul S" on Airbnb with "Rahul Sharma" on WhatsApp) lives at the
-- application layer, not the database, because it may require fuzzy matching
-- and human confirmation. The schema supports this by allowing multiple
-- channel identities per guest and a UNIQUE constraint only at the
-- (channel, external_id) level.
--
-- Second hardest: AI audit trail vs. message table bloat
-- -------------------------------------------------------
-- I debated keeping all AI fields inside the messages table vs. a separate
-- ai_interaction_log. I kept key operational fields (confidence_score, query_type,
-- handling_status, ai_drafted_reply) in messages for fast querying by agents,
-- and moved verbose data (full prompts, raw responses, token counts) to
-- ai_interaction_log. This keeps the messages table fast to query without
-- sacrificing full auditability.
