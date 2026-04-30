# Barber App — Phase 1

Android-first React Native (Expo) app for independent barbers. Offline-first with Supabase sync.

## Stack

| Layer | Tech |
|---|---|
| Mobile | React Native (Expo SDK 51) |
| Backend | Supabase (auth, database, storage) |
| Local DB | expo-sqlite (WAL mode) |
| State | Zustand |
| Language | TypeScript (strict) |

## Features

- **Appointment Book** — time-blocked daily schedule, walk-in one-tap, status updates
- **Client Book** — searchable client list, visit history, notes
- **Portfolio** — photo grid with style tags, before/after, visibility control
- **Payments** — record cash/card/wallet, daily total, service breakdown
- **Availability & Booking Link** — weekly grid, blocked dates, shareable booking URL
- **Before/After Capture** — dual-step camera with face-alignment overlay, Phase 2 hooks in place
- **Onboarding** — no login wall, fully operational in under 15 minutes
- **Simple / Advanced toggle** — per-screen, preference saved locally
- **Offline-first sync** — SQLite → Supabase sync queue, green/amber indicator

## Setup

### 1. Prerequisites

```bash
npm install -g expo-cli
npm install
```

### 2. Environment

Copy `.env.example` to `.env` and fill in your Supabase project credentials:

```
EXPO_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
```

### 3. Supabase

a. Create a new Supabase project at https://supabase.com  
b. In the SQL editor, run the migrations in order:

```
supabase/migrations/001_initial_schema.sql
supabase/migrations/002_indexes.sql
```

c. Create storage buckets in the Supabase dashboard:
- `portfolio-photos` (public)
- `capture-photos` (private)
- `profile-photos` (public)

d. Enable Email auth (or anonymous auth for Phase 1 background account creation).

### 4. Run

```bash
# Android (recommended)
npx expo start --android

# Or scan QR with Expo Go
npx expo start
```

## Project Structure

```
App.tsx                  # Entry: DB init, onboarding gate, sync listener
src/
  types/index.ts         # All TypeScript interfaces
  theme/colors.ts        # Design tokens (dark theme)
  database/
    schema.ts            # SQLite CREATE TABLE statements
    db.ts                # All CRUD operations
    sync.ts              # Sync queue → Supabase flush
  lib/supabase.ts        # Supabase client
  store/useStore.ts      # Zustand global state
  navigation/
    RootNavigator.tsx    # 5-tab bottom bar
  components/
    ScreenHeader.tsx     # Title + sync dot + advanced toggle
    SyncIndicator.tsx    # Green/amber/dim dot
    AdvancedToggle.tsx   # Simple/Advanced pill button
    FAB.tsx              # Floating action button
  screens/
    onboarding/OnboardingScreen.tsx
    HomeScreen.tsx
    AppointmentsScreen.tsx
    ClientsScreen.tsx
    PortfolioScreen.tsx
    PaymentsScreen.tsx
    AvailabilityScreen.tsx
    CaptureScreen.tsx
    SettingsScreen.tsx
supabase/migrations/
  001_initial_schema.sql
  002_indexes.sql
```

## Offline Behavior

- All writes go to SQLite immediately — UI never blocks on network
- `sync_queue` table accumulates operations while offline
- On app foreground / connectivity: `flushSyncQueue()` replays to Supabase
- Conflict resolution: last-write-wins on all fields except `appointment.status` (server authoritative)
- Sync indicator: green = fully synced, amber = pending operations

## Design System

- Dark theme default (`#0a0a0a` background)
- Primary accent: `#d4a843` (gold)
- Minimum tap target: 48px
- Simple view default, Advanced toggle per screen
- All modals slide from bottom sheet

## Phase 2 Hooks (already in codebase, not active)

- `capture_sessions.consistency_score` — column exists, null in Phase 1
- `capture_sessions.gpt_simulation_url` — column exists, null in Phase 1
- Capture screen shows locked feature cards with "Available after 50 captures" and "Coming in next update" labels
- `auto_published` flag is live (controls portfolio visibility)

## Phase 1 Success Gates

| Metric | Target |
|---|---|
| Before/after pairs captured | 500+ |
| Client records with 3+ visits | Average across active barbers |
| Appointment completion rate logged | >80% |
| Barbers active for 30+ days | 50+ |
