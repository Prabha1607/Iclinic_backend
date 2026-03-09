-- =============================================================================
-- 0009_create_appointments.sql
-- =============================================================================

CREATE TABLE appointments (
    id                   SERIAL            PRIMARY KEY,
    patient_id           INTEGER           NOT NULL REFERENCES users(id),
    provider_id          INTEGER           NOT NULL REFERENCES users(id),
    appointment_type_id  INTEGER           NOT NULL REFERENCES appointment_types(id),
    availability_slot_id INTEGER           NOT NULL REFERENCES available_slots(id),
    scheduled_date       DATE              NOT NULL,
    scheduled_start_time TIME              NOT NULL,
    scheduled_end_time   TIME              NOT NULL,
    status               appointmentstatus NOT NULL DEFAULT 'SCHEDULED',
    reason_for_visit     TEXT,
    notes                TEXT,
    booking_channel      bookingchannel,
    instructions         TEXT,
    cancelled_at         TIMESTAMPTZ,
    cancellation_reason  TEXT,
    is_active            BOOLEAN           NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ       NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ       NOT NULL DEFAULT now()
);

CREATE INDEX ix_appointments_patient_id           ON appointments (patient_id);
CREATE INDEX ix_appointments_provider_id          ON appointments (provider_id);
CREATE INDEX ix_appointments_appointment_type_id  ON appointments (appointment_type_id);
CREATE INDEX ix_appointments_availability_slot_id ON appointments (availability_slot_id);
CREATE INDEX ix_appointments_scheduled_date       ON appointments (scheduled_date);
CREATE INDEX ix_appointments_status               ON appointments (status);