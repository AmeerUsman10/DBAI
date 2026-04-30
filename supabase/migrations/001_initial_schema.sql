-- Barber App Phase 1 — Supabase Migration
-- Run in Supabase SQL editor or via supabase db push

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Barbers
CREATE TABLE IF NOT EXISTS barbers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  shop_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  profile_photo_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  synced_at TIMESTAMPTZ
);

-- Services
CREATE TABLE IF NOT EXISTS services (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  price NUMERIC(10,2) NOT NULL,
  duration_minutes INTEGER NOT NULL DEFAULT 30
);

-- Clients
CREATE TABLE IF NOT EXISTS clients (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  phone TEXT NOT NULL,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Appointments
CREATE TABLE IF NOT EXISTS appointments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
  date DATE NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  status TEXT NOT NULL DEFAULT 'scheduled'
    CHECK (status IN ('scheduled','completed','cancelled','no_show')),
  walk_in BOOLEAN NOT NULL DEFAULT FALSE,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Visits
CREATE TABLE IF NOT EXISTS visits (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
  date DATE NOT NULL,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
  amount_paid NUMERIC(10,2) NOT NULL,
  payment_method TEXT NOT NULL
    CHECK (payment_method IN ('cash','card','wallet')),
  notes TEXT
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  visit_id UUID NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  amount NUMERIC(10,2) NOT NULL,
  method TEXT NOT NULL CHECK (method IN ('cash','card','wallet')),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Portfolio items
CREATE TABLE IF NOT EXISTS portfolio_items (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
  visit_id UUID REFERENCES visits(id) ON DELETE SET NULL,
  photo_before_url TEXT,
  photo_after_url TEXT NOT NULL,
  style_tag TEXT NOT NULL DEFAULT 'other'
    CHECK (style_tag IN ('fade','taper','curl','beard','color','other')),
  visibility TEXT NOT NULL DEFAULT 'private'
    CHECK (visibility IN ('public','private')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Availability
CREATE TABLE IF NOT EXISTS availability (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (barber_id, day_of_week)
);

-- Blocked dates
CREATE TABLE IF NOT EXISTS blocked_dates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  reason TEXT,
  UNIQUE (barber_id, date)
);

-- Booking settings
CREATE TABLE IF NOT EXISTS booking_settings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL UNIQUE REFERENCES barbers(id) ON DELETE CASCADE,
  buffer_minutes INTEGER NOT NULL DEFAULT 0,
  require_deposit BOOLEAN NOT NULL DEFAULT FALSE,
  deposit_amount NUMERIC(10,2) NOT NULL DEFAULT 0,
  cancellation_policy_text TEXT,
  reminder_enabled BOOLEAN NOT NULL DEFAULT FALSE
);

-- Capture sessions (Phase 1 — AI columns stored null)
CREATE TABLE IF NOT EXISTS capture_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  barber_id UUID NOT NULL REFERENCES barbers(id) ON DELETE CASCADE,
  client_id UUID REFERENCES clients(id) ON DELETE SET NULL,
  appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
  photo_before_url TEXT,
  photo_after_url TEXT,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  paired BOOLEAN NOT NULL DEFAULT FALSE,
  auto_published BOOLEAN NOT NULL DEFAULT FALSE,
  -- Phase 2 fields (null in Phase 1)
  consistency_score NUMERIC(5,2),
  gpt_simulation_url TEXT
);

-- ──────────────────────────────────────────────
-- Row Level Security
-- ──────────────────────────────────────────────

ALTER TABLE barbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE services ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE availability ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocked_dates ENABLE ROW LEVEL SECURITY;
ALTER TABLE booking_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE capture_sessions ENABLE ROW LEVEL SECURITY;

-- Barbers: own row only
CREATE POLICY "barber_own" ON barbers
  FOR ALL USING (id::text = auth.uid()::text);

-- All barber-owned tables: barber_id matches auth uid
CREATE POLICY "services_own" ON services
  FOR ALL USING (barber_id::text = auth.uid()::text);

CREATE POLICY "clients_own" ON clients
  FOR ALL USING (barber_id::text = auth.uid()::text);

CREATE POLICY "appointments_own" ON appointments
  FOR ALL USING (barber_id::text = auth.uid()::text);

CREATE POLICY "visits_own" ON visits
  FOR ALL USING (
    client_id IN (
      SELECT id FROM clients WHERE barber_id::text = auth.uid()::text
    )
  );

CREATE POLICY "payments_own" ON payments
  FOR ALL USING (
    visit_id IN (
      SELECT v.id FROM visits v
      JOIN clients c ON c.id = v.client_id
      WHERE c.barber_id::text = auth.uid()::text
    )
  );

CREATE POLICY "portfolio_own" ON portfolio_items
  FOR ALL USING (barber_id::text = auth.uid()::text);

-- Public portfolio items readable by anyone (for booking page)
CREATE POLICY "portfolio_public_read" ON portfolio_items
  FOR SELECT USING (visibility = 'public');

CREATE POLICY "availability_own" ON availability
  FOR ALL USING (barber_id::text = auth.uid()::text);

-- Availability publicly readable (booking page needs it)
CREATE POLICY "availability_public_read" ON availability
  FOR SELECT USING (TRUE);

CREATE POLICY "blocked_dates_own" ON blocked_dates
  FOR ALL USING (barber_id::text = auth.uid()::text);

CREATE POLICY "blocked_dates_public_read" ON blocked_dates
  FOR SELECT USING (TRUE);

CREATE POLICY "booking_settings_own" ON booking_settings
  FOR ALL USING (barber_id::text = auth.uid()::text);

CREATE POLICY "booking_settings_public_read" ON booking_settings
  FOR SELECT USING (TRUE);

CREATE POLICY "capture_sessions_own" ON capture_sessions
  FOR ALL USING (barber_id::text = auth.uid()::text);

-- ──────────────────────────────────────────────
-- Storage buckets
-- ──────────────────────────────────────────────

-- Run via Supabase dashboard or storage API:
-- Create bucket: portfolio-photos (public)
-- Create bucket: capture-photos (private)
-- Create bucket: profile-photos (public)
