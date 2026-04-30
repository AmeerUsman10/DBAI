# Deployment Guide

## Android Build (EAS Build)

### 1. Install EAS CLI

```bash
npm install -g eas-cli
eas login
```

### 2. Configure EAS

```bash
eas build:configure
```

This creates `eas.json`. Use this configuration:

```json
{
  "cli": { "version": ">= 10.0.0" },
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "android": { "buildType": "apk" }
    },
    "preview": {
      "distribution": "internal",
      "android": { "buildType": "apk" }
    },
    "production": {
      "android": { "buildType": "app-bundle" }
    }
  },
  "submit": {
    "production": {}
  }
}
```

### 3. Set environment secrets in EAS

```bash
eas secret:create --scope project --name EXPO_PUBLIC_SUPABASE_URL --value <your-url>
eas secret:create --scope project --name EXPO_PUBLIC_SUPABASE_ANON_KEY --value <your-key>
```

### 4. Build

```bash
# Internal preview APK (side-loadable)
eas build --platform android --profile preview

# Production AAB for Play Store
eas build --platform android --profile production
```

### 5. Submit to Play Store

```bash
eas submit --platform android
```

Requires a Google Play service account key configured in EAS.

---

## Supabase Production Checklist

- [ ] Run `001_initial_schema.sql` and `002_indexes.sql`
- [ ] Create storage buckets: `portfolio-photos` (public), `capture-photos` (private), `profile-photos` (public)
- [ ] Enable RLS on all tables (migrations include this)
- [ ] Set up Supabase Auth — enable Anonymous sign-ins for background account creation
- [ ] Configure SMTP for email confirmations (optional Phase 1)
- [ ] Set up Storage CORS for web booking page
- [ ] Enable Point-in-Time Recovery on Pro plan before going live

---

## Web Booking Page (Phase 1 stub)

The booking link format is: `https://book.barberapp.co/<barber_id>`

This page is a minimal web app (not included in this repo) that:
1. Reads `availability` and `blocked_dates` for the barber (public RLS policy)
2. Shows open slots based on service durations
3. Client enters name + phone → inserts into `appointments` table
4. Triggers a confirmation SMS via Supabase Edge Function (Twilio)

The mobile app receives the new appointment via Supabase Realtime or on next foreground sync.

---

## Environment Variables Reference

| Variable | Description |
|---|---|
| `EXPO_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `EXPO_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon (public) key |

All `EXPO_PUBLIC_*` variables are bundled into the app. Never put service-role keys here.
