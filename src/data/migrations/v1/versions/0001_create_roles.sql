-- =============================================================================
-- 0001_create_roles.sql
-- =============================================================================

CREATE TABLE roles (
    id         SERIAL       PRIMARY KEY,
    role_name  VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX ix_roles_role_name ON roles (role_name);