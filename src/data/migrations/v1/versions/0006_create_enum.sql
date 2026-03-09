-- =============================================================================
-- 0006_create_enums.sql
-- =============================================================================

CREATE TYPE appointmentstatus AS ENUM (
    'SCHEDULED',
    'CONFIRMED',
    'COMPLETED',
    'CANCELLED',
    'NO_SHOW'
);

CREATE TYPE bookingchannel AS ENUM (
    'APP',
    'CALL',
    'WALK_IN'
);

CREATE TYPE slotstatus AS ENUM (
    'AVAILABLE',
    'BOOKED',
    'BLOCKED'
);