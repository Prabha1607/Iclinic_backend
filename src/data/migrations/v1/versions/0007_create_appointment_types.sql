-- =============================================================================
-- 0007_create_appointment_types.sql
-- =============================================================================

CREATE TABLE appointment_types (
    id               SERIAL       PRIMARY KEY,
    provider_id      INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name             VARCHAR(100) NOT NULL,
    description      TEXT,
    duration_minutes INTEGER      NOT NULL,
    instructions     VARCHAR(255),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX ix_appointment_types_provider_id ON appointment_types (provider_id);