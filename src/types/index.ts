export type Status = 'scheduled' | 'completed' | 'cancelled' | 'no_show';
export type PaymentMethod = 'cash' | 'card' | 'wallet';
export type StyleTag = 'fade' | 'taper' | 'curl' | 'beard' | 'color' | 'other';
export type Visibility = 'public' | 'private';
export type Currency = 'PKR' | 'INR' | 'USD' | 'EUR' | 'GBP' | 'AED' | 'SAR';

export interface Barber {
  id: string;
  name: string;
  shop_name: string;
  phone: string;
  profile_photo_url?: string;
  created_at: string;
  synced_at?: string;
}

export interface Service {
  id: string;
  barber_id: string;
  name: string;
  price: number;
  duration_minutes: number;
}

export interface Client {
  id: string;
  barber_id: string;
  name: string;
  phone: string;
  notes?: string;
  created_at: string;
}

export interface Appointment {
  id: string;
  barber_id: string;
  client_id?: string;
  service_id: string;
  date: string;
  start_time: string;
  end_time: string;
  status: Status;
  walk_in: boolean;
  notes?: string;
  created_at: string;
}

export interface Visit {
  id: string;
  barber_id: string;
  client_id?: string;
  appointment_id?: string;
  date: string;
  service_id: string;
  amount_paid: number;
  payment_method: PaymentMethod;
  notes?: string;
}

export interface Payment {
  id: string;
  visit_id: string;
  amount: number;
  method: PaymentMethod;
  recorded_at: string;
}

export interface PortfolioItem {
  id: string;
  barber_id: string;
  client_id?: string;
  visit_id?: string;
  photo_before_url?: string;
  photo_after_url: string;
  style_tag: StyleTag;
  visibility: Visibility;
  created_at: string;
}

export interface Availability {
  id: string;
  barber_id: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface BlockedDate {
  id: string;
  barber_id: string;
  date: string;
  reason?: string;
}

export interface BookingSettings {
  id: string;
  barber_id: string;
  buffer_minutes: number;
  require_deposit: boolean;
  deposit_amount: number;
  cancellation_policy_text?: string;
  reminder_enabled: boolean;
  currency: Currency;
}

export interface CaptureSession {
  id: string;
  barber_id: string;
  client_id?: string;
  appointment_id?: string;
  photo_before_url?: string;
  photo_after_url?: string;
  captured_at: string;
  paired: boolean;
  consistency_score?: number;
  gpt_simulation_url?: string;
  auto_published: boolean;
}

export type SyncStatus = 'synced' | 'pending' | 'offline';

export interface SyncQueueItem {
  id: string;
  table_name: string;
  record_id: string;
  operation: 'insert' | 'update' | 'delete';
  payload: string;
  created_at: string;
  attempts: number;
}
