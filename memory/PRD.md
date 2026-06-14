# Éva — Behavior Tax (PRD)

## Vision
Éva is an automatic behavior-tax layer on top of the user's bank. Every spending decision becomes a visible trade-off, with a tiny tax routed into the user's savings goal — without manual data entry.

## Architecture (read-and-react loop)
1. User links a bank (Revolut sandbox via API key, or Spuerkeess stubbed).
2. `POST /api/bank/sync` pulls new transactions and deduplicates by `provider_txn_id`.
3. `POST /api/tax/process` matches each `raw_transaction` to a category by keyword, applies a repetition-aware tax (`base + hit_count × rep_increment`, capped at `max_tax_rate`), enforces `daily_cap_amount`, writes a `tax_event`, and credits the active savings bucket.
4. Activity feed (`GET /api/activity`) shows each detected purchase, the tax taken, the rep-count, the cap status, and a 10-minute Override button.
5. `POST /api/tax/override/:event_id` (within 10 min) rolls the tax back. `POST /api/tax/transfer` marks pending events as transferred (stub — no real money movement yet).

## MVP scope (this build)
- JWT email/password auth, currency picked at signup.
- Bank linking: Revolut (real sandbox HTTP) + Spuerkeess (deterministic 7-merchant stub).
- Categories with `merchant_keywords`, `rep_increment`, `max_tax_rate`, `daily_cap_amount`. 7 seeded defaults including the keyword lists from PRD.
- Tax engine with repetition counters (`daily_repetition_counters`) and daily caps shaved to remaining cap.
- Activity feed UI (Saved · Skipped — cap reached · Overridden · Unmatched).
- Multiple savings buckets, Future Value visualiser, Insights screen.
- 10-minute intentional-spend Override (toast feedback, rollback to bucket).
- Transfer stub endpoint (`tax_transfers` collection, status `simulated`).

## Tech stack
- Frontend: Expo SDK 54, expo-router, expo-image, expo-linear-gradient, expo-font.
- Backend: FastAPI + Motor (MongoDB), python-jose JWT, passlib bcrypt, sync HTTP via `requests` in threadpool for Revolut.
- All API routes under `/api/*`. Frontend uses `EXPO_PUBLIC_BACKEND_URL`.

## MongoDB collections
- `users`, `categories`, `buckets` (existing, extended).
- `linked_accounts` — id, user_id, provider, access_token, is_active, linked_at.
- `raw_transactions` — id, user_id, account_id, provider_txn_id, merchant_name, amount, currency, transacted_at, ingested_at, matched_category_id, status (pending|taxed|skipped|unmatched).
- `daily_repetition_counters` — id, user_id, category_id, counter_date (ISO date string), hit_count.
- `tax_events` — id, user_id, raw_txn_id, category_id, category_name, bucket_id, original_amount, tax_rate_applied, tax_amount, repetition_number, status (pending|transferred|overridden), override_reason, transacted_at, created_at.
- `tax_transfers` — id, user_id, total_amount, tax_event_ids[], status (simulated), executed_at.

## API surface (relevant changes)
- Bank: `POST /api/bank/link`, `GET /api/bank/accounts`, `DELETE /api/bank/accounts/:id`, `POST /api/bank/sync`.
- Tax: `POST /api/tax/process`, `POST /api/tax/override/:event_id`, `POST /api/tax/transfer`.
- Feed: `GET /api/activity`.
- Removed: `POST /api/transactions` (manual entry — no longer part of the product).

## Out of scope (deferred)
- Real outbound payments (Stripe Connect / SEPA).
- Production Revolut/PSD2 OAuth flows.
- AI insights, recurring schedules, multi-account budgeting, push notifications.
