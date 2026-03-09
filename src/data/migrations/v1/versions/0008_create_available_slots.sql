-- =============================================================================
-- 0008_create_available_slots.sql
-- =============================================================================

CREATE TABLE available_slots (
    id                SERIAL      PRIMARY KEY,
    provider_id       INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    availability_date DATE        NOT NULL,
    start_time        TIME        NOT NULL,
    end_time          TIME        NOT NULL,
    status            slotstatus  NOT NULL DEFAULT 'AVAILABLE',
    created_by        INTEGER     REFERENCES users(id),
    notes             TEXT,
    is_active         BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_available_slots_provider_id       ON available_slots (provider_id);
CREATE INDEX ix_available_slots_availability_date ON available_slots (availability_date);
CREATE INDEX ix_available_slots_status            ON available_slots (status);