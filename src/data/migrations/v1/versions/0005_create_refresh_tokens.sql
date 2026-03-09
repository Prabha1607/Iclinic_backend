-- =============================================================================
-- 0003_create_patient_profiles.sql
-- =============================================================================

CREATE TABLE patient_profiles (
    id                  SERIAL       PRIMARY KEY,
    user_id             INTEGER      NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    date_of_birth       DATE,
    gender              VARCHAR(20),
    address             VARCHAR(255),
    preferred_language  VARCHAR(50),
    last_login_at       TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ
);

CREATE INDEX ix_patient_profiles_user_id ON patient_profiles (user_id);