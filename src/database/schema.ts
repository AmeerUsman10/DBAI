import * as SQLite from 'expo-sqlite';

let db: SQLite.SQLiteDatabase | null = null;

export function getDb(): SQLite.SQLiteDatabase {
  if (!db) {
    db = SQLite.openDatabaseSync('barber.db');
  }
  return db;
}

export async function initDb(): Promise<void> {
  const database = getDb();

  await database.execAsync(`
    PRAGMA journal_mode = WAL;
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS barbers (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      shop_name TEXT NOT NULL,
      phone TEXT NOT NULL,
      profile_photo_url TEXT,
      created_at TEXT NOT NULL,
      synced_at TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      name TEXT NOT NULL,
      price REAL NOT NULL,
      duration_minutes INTEGER NOT NULL DEFAULT 30
    );

    CREATE TABLE IF NOT EXISTS clients (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      name TEXT NOT NULL,
      phone TEXT NOT NULL,
      notes TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS appointments (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      client_id TEXT,
      service_id TEXT NOT NULL,
      date TEXT NOT NULL,
      start_time TEXT NOT NULL,
      end_time TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'scheduled',
      walk_in INTEGER NOT NULL DEFAULT 0,
      notes TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS visits (
      id TEXT PRIMARY KEY,
      client_id TEXT NOT NULL,
      appointment_id TEXT,
      date TEXT NOT NULL,
      service_id TEXT NOT NULL,
      amount_paid REAL NOT NULL,
      payment_method TEXT NOT NULL,
      notes TEXT
    );

    CREATE TABLE IF NOT EXISTS payments (
      id TEXT PRIMARY KEY,
      visit_id TEXT NOT NULL,
      amount REAL NOT NULL,
      method TEXT NOT NULL,
      recorded_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS portfolio_items (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      client_id TEXT,
      visit_id TEXT,
      photo_before_url TEXT,
      photo_after_url TEXT NOT NULL,
      style_tag TEXT NOT NULL DEFAULT 'other',
      visibility TEXT NOT NULL DEFAULT 'private',
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS availability (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      day_of_week INTEGER NOT NULL,
      start_time TEXT NOT NULL,
      end_time TEXT NOT NULL,
      is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS blocked_dates (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      date TEXT NOT NULL,
      reason TEXT
    );

    CREATE TABLE IF NOT EXISTS booking_settings (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL UNIQUE,
      buffer_minutes INTEGER NOT NULL DEFAULT 0,
      require_deposit INTEGER NOT NULL DEFAULT 0,
      deposit_amount REAL NOT NULL DEFAULT 0,
      cancellation_policy_text TEXT,
      reminder_enabled INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS capture_sessions (
      id TEXT PRIMARY KEY,
      barber_id TEXT NOT NULL,
      client_id TEXT,
      appointment_id TEXT,
      photo_before_url TEXT,
      photo_after_url TEXT,
      captured_at TEXT NOT NULL,
      paired INTEGER NOT NULL DEFAULT 0,
      auto_published INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS sync_queue (
      id TEXT PRIMARY KEY,
      table_name TEXT NOT NULL,
      record_id TEXT NOT NULL,
      operation TEXT NOT NULL,
      payload TEXT NOT NULL,
      created_at TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS app_state (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
}
