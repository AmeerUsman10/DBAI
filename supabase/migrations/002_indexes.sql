-- Indexes for common query patterns

CREATE INDEX IF NOT EXISTS idx_appointments_barber_date
  ON appointments(barber_id, date);

CREATE INDEX IF NOT EXISTS idx_visits_client
  ON visits(client_id);

CREATE INDEX IF NOT EXISTS idx_visits_date
  ON visits(date);

CREATE INDEX IF NOT EXISTS idx_portfolio_barber
  ON portfolio_items(barber_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_clients_barber
  ON clients(barber_id, name);

CREATE INDEX IF NOT EXISTS idx_capture_barber
  ON capture_sessions(barber_id, captured_at DESC);
