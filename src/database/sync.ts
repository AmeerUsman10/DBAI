import { getDb } from './schema';
import { createClient } from '@supabase/supabase-js';
import type { SyncQueueItem } from '../types';
import uuid from 'react-native-uuid';

const SUPABASE_URL = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
const SUPABASE_ANON_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '';

let supabase: ReturnType<typeof createClient> | null = null;

function getSupabase() {
  if (!supabase && SUPABASE_URL && SUPABASE_ANON_KEY) {
    supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
  return supabase;
}

export async function enqueueSyncOp(
  tableName: string,
  recordId: string,
  operation: SyncQueueItem['operation'],
  payload: object
): Promise<void> {
  const db = getDb();
  const item: SyncQueueItem = {
    id: uuid.v4() as string,
    table_name: tableName,
    record_id: recordId,
    operation,
    payload: JSON.stringify(payload),
    created_at: new Date().toISOString(),
    attempts: 0,
  };
  await db.runAsync(
    `INSERT INTO sync_queue (id, table_name, record_id, operation, payload, created_at, attempts)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [item.id, item.table_name, item.record_id, item.operation, item.payload, item.created_at, item.attempts]
  );
}

export async function getPendingCount(): Promise<number> {
  const row = await getDb().getFirstAsync<{ count: number }>(
    'SELECT COUNT(*) as count FROM sync_queue'
  );
  return row?.count ?? 0;
}

export async function flushSyncQueue(): Promise<void> {
  const client = getSupabase();
  if (!client) return;

  const db = getDb();
  const items = await db.getAllAsync<SyncQueueItem>(
    'SELECT * FROM sync_queue ORDER BY created_at ASC LIMIT 50'
  );

  for (const item of items) {
    try {
      const payload = JSON.parse(item.payload);
      if (item.operation === 'insert') {
        await client.from(item.table_name).upsert(payload);
      } else if (item.operation === 'update') {
        await client.from(item.table_name).update(payload).eq('id', item.record_id);
      } else if (item.operation === 'delete') {
        await client.from(item.table_name).delete().eq('id', item.record_id);
      }
      await db.runAsync('DELETE FROM sync_queue WHERE id = ?', [item.id]);
    } catch {
      await db.runAsync(
        'UPDATE sync_queue SET attempts = attempts + 1 WHERE id = ?',
        [item.id]
      );
    }
  }
}
