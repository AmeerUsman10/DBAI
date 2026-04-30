import { getDb } from './schema';
import type {
  Barber, Service, Client, Appointment, Visit, Payment,
  PortfolioItem, Availability, BlockedDate, BookingSettings,
  CaptureSession, SyncQueueItem
} from '../types';
import { enqueueSyncOp } from './sync';
import uuid from 'react-native-uuid';

const now = () => new Date().toISOString();
const id = () => uuid.v4() as string;

// ── Barber ─────────────────────────────────────────────────────────────────

export async function saveBarber(data: Omit<Barber, 'id' | 'created_at'>): Promise<Barber> {
  const db = getDb();
  const barber: Barber = { ...data, id: id(), created_at: now() };
  await db.runAsync(
    `INSERT OR REPLACE INTO barbers (id, name, shop_name, phone, profile_photo_url, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`,
    [barber.id, barber.name, barber.shop_name, barber.phone, barber.profile_photo_url ?? null, barber.created_at]
  );
  await enqueueSyncOp('barbers', barber.id, 'insert', barber);
  return barber;
}

export async function getBarber(): Promise<Barber | null> {
  const db = getDb();
  const row = await db.getFirstAsync<Barber>('SELECT * FROM barbers LIMIT 1');
  return row ?? null;
}

export async function updateBarber(id: string, data: Partial<Barber>): Promise<void> {
  const db = getDb();
  const fields = Object.keys(data).map(k => `${k} = ?`).join(', ');
  const values = [...Object.values(data), id];
  await db.runAsync(`UPDATE barbers SET ${fields} WHERE id = ?`, values);
  await enqueueSyncOp('barbers', id, 'update', data);
}

// ── Services ────────────────────────────────────────────────────────────────

export async function createService(data: Omit<Service, 'id'>): Promise<Service> {
  const db = getDb();
  const service: Service = { ...data, id: id() };
  await db.runAsync(
    `INSERT INTO services (id, barber_id, name, price, duration_minutes) VALUES (?, ?, ?, ?, ?)`,
    [service.id, service.barber_id, service.name, service.price, service.duration_minutes]
  );
  await enqueueSyncOp('services', service.id, 'insert', service);
  return service;
}

export async function getServices(barber_id: string): Promise<Service[]> {
  const db = getDb();
  return db.getAllAsync<Service>('SELECT * FROM services WHERE barber_id = ?', [barber_id]);
}

export async function updateService(serviceId: string, data: Partial<Service>): Promise<void> {
  const db = getDb();
  const fields = Object.keys(data).map(k => `${k} = ?`).join(', ');
  await db.runAsync(`UPDATE services SET ${fields} WHERE id = ?`, [...Object.values(data), serviceId]);
  await enqueueSyncOp('services', serviceId, 'update', data);
}

export async function deleteService(serviceId: string): Promise<void> {
  const db = getDb();
  await db.runAsync('DELETE FROM services WHERE id = ?', [serviceId]);
  await enqueueSyncOp('services', serviceId, 'delete', {});
}

// ── Clients ─────────────────────────────────────────────────────────────────

export async function createClient(data: Omit<Client, 'id' | 'created_at'>): Promise<Client> {
  const db = getDb();
  const client: Client = { ...data, id: id(), created_at: now() };
  await db.runAsync(
    `INSERT INTO clients (id, barber_id, name, phone, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)`,
    [client.id, client.barber_id, client.name, client.phone, client.notes ?? null, client.created_at]
  );
  await enqueueSyncOp('clients', client.id, 'insert', client);
  return client;
}

export async function getClients(barber_id: string): Promise<Client[]> {
  return getDb().getAllAsync<Client>('SELECT * FROM clients WHERE barber_id = ? ORDER BY name ASC', [barber_id]);
}

export async function searchClients(barber_id: string, query: string): Promise<Client[]> {
  const q = `%${query}%`;
  return getDb().getAllAsync<Client>(
    'SELECT * FROM clients WHERE barber_id = ? AND (name LIKE ? OR phone LIKE ?) ORDER BY name ASC',
    [barber_id, q, q]
  );
}

export async function updateClient(clientId: string, data: Partial<Client>): Promise<void> {
  const db = getDb();
  const fields = Object.keys(data).map(k => `${k} = ?`).join(', ');
  await db.runAsync(`UPDATE clients SET ${fields} WHERE id = ?`, [...Object.values(data), clientId]);
  await enqueueSyncOp('clients', clientId, 'update', data);
}

// ── Appointments ─────────────────────────────────────────────────────────────

export async function createAppointment(data: Omit<Appointment, 'id' | 'created_at'>): Promise<Appointment> {
  const db = getDb();
  const appt: Appointment = { ...data, id: id(), created_at: now() };
  await db.runAsync(
    `INSERT INTO appointments (id, barber_id, client_id, service_id, date, start_time, end_time, status, walk_in, notes, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [appt.id, appt.barber_id, appt.client_id ?? null, appt.service_id, appt.date,
     appt.start_time, appt.end_time, appt.status, appt.walk_in ? 1 : 0, appt.notes ?? null, appt.created_at]
  );
  await enqueueSyncOp('appointments', appt.id, 'insert', appt);
  return appt;
}

export async function getAppointmentsForDate(barber_id: string, date: string): Promise<Appointment[]> {
  const rows = await getDb().getAllAsync<any>(
    `SELECT * FROM appointments WHERE barber_id = ? AND date = ? ORDER BY start_time ASC`,
    [barber_id, date]
  );
  return rows.map(r => ({ ...r, walk_in: !!r.walk_in }));
}

export async function updateAppointmentStatus(apptId: string, status: Appointment['status']): Promise<void> {
  await getDb().runAsync('UPDATE appointments SET status = ? WHERE id = ?', [status, apptId]);
  await enqueueSyncOp('appointments', apptId, 'update', { status });
}

// ── Visits ───────────────────────────────────────────────────────────────────

export async function createVisit(data: Omit<Visit, 'id'>): Promise<Visit> {
  const db = getDb();
  const visit: Visit = { ...data, id: id() };
  await db.runAsync(
    `INSERT INTO visits (id, client_id, appointment_id, date, service_id, amount_paid, payment_method, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [visit.id, visit.client_id, visit.appointment_id ?? null, visit.date,
     visit.service_id, visit.amount_paid, visit.payment_method, visit.notes ?? null]
  );
  await enqueueSyncOp('visits', visit.id, 'insert', visit);
  return visit;
}

export async function getVisitsForClient(client_id: string): Promise<Visit[]> {
  return getDb().getAllAsync<Visit>('SELECT * FROM visits WHERE client_id = ? ORDER BY date DESC', [client_id]);
}

export async function getDailyTotal(barber_id: string, date: string): Promise<number> {
  const row = await getDb().getFirstAsync<{ total: number }>(
    `SELECT COALESCE(SUM(v.amount_paid), 0) as total
     FROM visits v
     JOIN appointments a ON a.id = v.appointment_id
     WHERE a.barber_id = ? AND v.date = ?`,
    [barber_id, date]
  );
  return row?.total ?? 0;
}

export async function getWeeklyTotals(barber_id: string): Promise<{ date: string; total: number }[]> {
  return getDb().getAllAsync<{ date: string; total: number }>(
    `SELECT v.date, COALESCE(SUM(v.amount_paid), 0) as total
     FROM visits v
     JOIN appointments a ON a.id = v.appointment_id
     WHERE a.barber_id = ?
       AND v.date >= date('now', '-6 days')
     GROUP BY v.date
     ORDER BY v.date ASC`,
    [barber_id]
  );
}

// ── Portfolio ─────────────────────────────────────────────────────────────────

export async function createPortfolioItem(data: Omit<PortfolioItem, 'id' | 'created_at'>): Promise<PortfolioItem> {
  const db = getDb();
  const item: PortfolioItem = { ...data, id: id(), created_at: now() };
  await db.runAsync(
    `INSERT INTO portfolio_items (id, barber_id, client_id, visit_id, photo_before_url, photo_after_url, style_tag, visibility, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [item.id, item.barber_id, item.client_id ?? null, item.visit_id ?? null,
     item.photo_before_url ?? null, item.photo_after_url, item.style_tag, item.visibility, item.created_at]
  );
  await enqueueSyncOp('portfolio_items', item.id, 'insert', item);
  return item;
}

export async function getPortfolioItems(barber_id: string): Promise<PortfolioItem[]> {
  return getDb().getAllAsync<PortfolioItem>(
    'SELECT * FROM portfolio_items WHERE barber_id = ? ORDER BY created_at DESC',
    [barber_id]
  );
}

export async function updatePortfolioVisibility(itemId: string, visibility: 'public' | 'private'): Promise<void> {
  await getDb().runAsync('UPDATE portfolio_items SET visibility = ? WHERE id = ?', [visibility, itemId]);
  await enqueueSyncOp('portfolio_items', itemId, 'update', { visibility });
}

// ── Availability ──────────────────────────────────────────────────────────────

export async function saveAvailability(items: Omit<Availability, 'id'>[]): Promise<void> {
  const db = getDb();
  for (const item of items) {
    const avail: Availability = { ...item, id: id() };
    await db.runAsync(
      `INSERT OR REPLACE INTO availability (id, barber_id, day_of_week, start_time, end_time, is_active)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [avail.id, avail.barber_id, avail.day_of_week, avail.start_time, avail.end_time, avail.is_active ? 1 : 0]
    );
  }
}

export async function getAvailability(barber_id: string): Promise<Availability[]> {
  const rows = await getDb().getAllAsync<any>(
    'SELECT * FROM availability WHERE barber_id = ? ORDER BY day_of_week ASC',
    [barber_id]
  );
  return rows.map(r => ({ ...r, is_active: !!r.is_active }));
}

export async function getBlockedDates(barber_id: string): Promise<BlockedDate[]> {
  return getDb().getAllAsync<BlockedDate>('SELECT * FROM blocked_dates WHERE barber_id = ?', [barber_id]);
}

export async function addBlockedDate(barber_id: string, date: string, reason?: string): Promise<BlockedDate> {
  const blocked: BlockedDate = { id: id(), barber_id, date, reason };
  await getDb().runAsync(
    'INSERT INTO blocked_dates (id, barber_id, date, reason) VALUES (?, ?, ?, ?)',
    [blocked.id, blocked.barber_id, blocked.date, blocked.reason ?? null]
  );
  await enqueueSyncOp('blocked_dates', blocked.id, 'insert', blocked);
  return blocked;
}

export async function removeBlockedDate(dateId: string): Promise<void> {
  await getDb().runAsync('DELETE FROM blocked_dates WHERE id = ?', [dateId]);
  await enqueueSyncOp('blocked_dates', dateId, 'delete', {});
}

export async function getBookingSettings(barber_id: string): Promise<BookingSettings | null> {
  const row = await getDb().getFirstAsync<any>(
    'SELECT * FROM booking_settings WHERE barber_id = ?',
    [barber_id]
  );
  if (!row) return null;
  return { ...row, require_deposit: !!row.require_deposit, reminder_enabled: !!row.reminder_enabled };
}

export async function saveBookingSettings(data: Omit<BookingSettings, 'id'>): Promise<void> {
  const settings: BookingSettings = { ...data, id: id() };
  await getDb().runAsync(
    `INSERT OR REPLACE INTO booking_settings
     (id, barber_id, buffer_minutes, require_deposit, deposit_amount, cancellation_policy_text, reminder_enabled)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [settings.id, settings.barber_id, settings.buffer_minutes,
     settings.require_deposit ? 1 : 0, settings.deposit_amount,
     settings.cancellation_policy_text ?? null, settings.reminder_enabled ? 1 : 0]
  );
  await enqueueSyncOp('booking_settings', settings.barber_id, 'update', data);
}

// ── Capture Sessions ─────────────────────────────────────────────────────────

export async function createCaptureSession(data: Omit<CaptureSession, 'id' | 'captured_at'>): Promise<CaptureSession> {
  const session: CaptureSession = { ...data, id: id(), captured_at: now() };
  await getDb().runAsync(
    `INSERT INTO capture_sessions
     (id, barber_id, client_id, appointment_id, photo_before_url, photo_after_url, captured_at, paired, auto_published)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [session.id, session.barber_id, session.client_id ?? null, session.appointment_id ?? null,
     session.photo_before_url ?? null, session.photo_after_url ?? null,
     session.captured_at, session.paired ? 1 : 0, session.auto_published ? 1 : 0]
  );
  await enqueueSyncOp('capture_sessions', session.id, 'insert', session);
  return session;
}

export async function updateCaptureSession(sessionId: string, data: Partial<CaptureSession>): Promise<void> {
  const db = getDb();
  const fields = Object.keys(data).map(k => `${k} = ?`).join(', ');
  await db.runAsync(`UPDATE capture_sessions SET ${fields} WHERE id = ?`, [...Object.values(data), sessionId]);
  await enqueueSyncOp('capture_sessions', sessionId, 'update', data);
}

// ── App State ─────────────────────────────────────────────────────────────────

export async function getAppState(key: string): Promise<string | null> {
  const row = await getDb().getFirstAsync<{ value: string }>(
    'SELECT value FROM app_state WHERE key = ?', [key]
  );
  return row?.value ?? null;
}

export async function setAppState(key: string, value: string): Promise<void> {
  await getDb().runAsync(
    'INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)', [key, value]
  );
}
