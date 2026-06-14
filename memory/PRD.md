# Éva — Behavior Tax (PRD)

## Vision
Éva is an automatic behavior-tax layer on top of the user's bank. Every spending decision becomes a visible trade-off, with a tax routed into the user's savings goal — without manual data entry. A behavioral profile lets the user dial the strength and ethics of that tax to match their goals.

## Architecture (read-and-react loop)
1. User links a bank — Revolut via OAuth (sandbox-oba personal API) or Spuerkeess (deterministic stub).
2. `POST /api/bank/sync` ingests transactions, deduping by `provider_txn_id`.
3. `POST /api/tax/process` matches each `raw_transaction` to a category by keyword, applies a repetition-aware tax (`base + hit_count × rep_increment`, capped at `max_tax_rate`), applies the behavioral profile multiplier, enforces `daily_cap_amount`, writes a `tax_event` with `profile_applied`, and credits the active savings bucket.
4. Activity feed (`GET /api/activity`) shows each detected purchase, the tax taken, the rep count, the cap status, the applied profile, and a 10-minute Override button.
5. `POST /api/tax/override/:event_id` rolls the tax back inside the window. `POST /api/tax/transfer` (or auto for Savings Beast) marks pending events as `transferred` and logs to `tax_transfers`.

## Behavioral profiles
Persisted on the user document (`profile_type`, default `balanced`). Applied AFTER repetition adjustment and BEFORE the cap shave.

| Profile | Multiplier | Notes |
|---|---|---|
| balanced | 1.0× | Defaults. |
| aggressive | 1.5× | On every effective tax rate; still bounded by `max_tax_rate`. |
| ethical | 1.4× on Fast Food / Clothes / Entertainment / **Ethical Penalty** | Other categories unchanged. |
| mindful | 0.5× | Halves all effective rates. |
| savings_beast | 1.5× + auto-transfer | If pending taxes > €5 after `process`, an immediate stub-transfer fires. |

`pause_all_taxes=true` short-circuits `/api/tax/process` with `{"paused": true}`.

## MVP scope (this build)
- JWT email/password auth, currency picked at signup.
- Bank linking:
  - **Revolut Open Banking personal sandbox**: `POST /api/bank/link {provider:'revolut'}` (no token) → returns `consent_url` (frontend opens it via `WebBrowser.openAuthSessionAsync`). Backend `GET /api/bank/revolut/callback` exchanges the code for `access_token`/`refresh_token`/`token_expires_at`, marks the account active, and renders an HTML page that deep-links back to `eva://bank-callback`. Sync refreshes the token via `POST /token` when expired.
  - Legacy direct-token mode preserved (tests + Spuerkeess always).
  - Spuerkeess deterministic 7-merchant stub unchanged.
- Categories: 8 defaults including **Ethical Penalty** (keywords: amazon, mcdonalds, kfc, primark, h&m, coca-cola, pepsi, nestlé, monsanto, shein; base 0.35, rep_inc 0.05, max 0.70, cap 20). `merchant_keywords` matched case-insensitive with Ethical Penalty checked first so explicit brand hits route to it.
- Settings: `GET/PATCH /api/settings` for `profile_type`, `transfer_frequency` (instant/daily/weekly), `pause_all_taxes`.
- Tax engine with repetition counters, daily caps, profile multiplier, auto-transfer for Savings Beast.
- Activity feed surfaces `profile_applied`, status badges (Saved · Skipped — cap reached · Overridden · Unmatched).
- 10-minute Override window (rolls back bucket increment).
- Dashboard hero shows profile mode label; activity rows show non-balanced profile badges.
- Settings tab (5th bottom tab) with profile cards (intensity meter 1–5), transfer-timing chips, bank connections (linked-at + Unlink + Add bank), and Danger Zone (pause toggle).

## Tech stack
- Frontend: Expo SDK 54, expo-router, expo-image, expo-linear-gradient, expo-font, expo-web-browser, react-native-safe-area-context.
- Backend: FastAPI + Motor (MongoDB), python-jose JWT, passlib bcrypt, sync HTTP via `requests` in threadpool for Revolut.
- Deep-link scheme: `eva://`. Callback page redirects to `eva://bank-callback?status=ok` to auto-close the in-app browser.
- All API routes under `/api/*`. Frontend uses `EXPO_PUBLIC_BACKEND_URL`.

## MongoDB collections
- `users` — id, email, password_hash, name, currency, default_bucket_id, **profile_type**, **transfer_frequency**, **pause_all_taxes**, created_at.
- `categories` — id, user_id, name, icon, tax_rate, merchant_keywords[], rep_increment, max_tax_rate, daily_cap_amount.
- `buckets` — id, user_id, name, target_amount, saved_amount, image_key, is_default, created_at.
- `linked_accounts` — id, user_id, provider, access_token, **refresh_token**, **token_expires_at**, is_active, **oauth_state**, **redirect_uri**, linked_at.
- `raw_transactions` — id, user_id, account_id, provider_txn_id, merchant_name, amount, currency, transacted_at, ingested_at, matched_category_id, status (pending|taxed|skipped|unmatched).
- `daily_repetition_counters` — id, user_id, category_id, counter_date (ISO), hit_count.
- `tax_events` — id, user_id, raw_txn_id, category_id, category_name, bucket_id, original_amount, tax_rate_applied, tax_amount, repetition_number, status (pending|transferred|overridden), override_reason, **profile_applied**, transacted_at, created_at.
- `tax_transfers` — id, user_id, total_amount, tax_event_ids[], status (simulated), executed_at, trigger ("manual"|"savings_beast_auto").

## API surface
- Auth: `POST /api/auth/register`, `POST /api/auth/login`, `GET/PATCH /api/auth/me`.
- Settings: `GET /api/settings`, `PATCH /api/settings`.
- Categories: `GET/POST/PATCH/DELETE /api/categories[/:id]`.
- Buckets: `GET/POST/PATCH/DELETE /api/buckets[/:id]`.
- Bank: `POST /api/bank/link`, `GET /api/bank/accounts`, `DELETE /api/bank/accounts/:id`, `GET /api/bank/revolut/callback`, `POST /api/bank/sync`.
- Tax: `POST /api/tax/process`, `POST /api/tax/override/:event_id`, `POST /api/tax/transfer`.
- Feed: `GET /api/activity`.
- Insights: `GET /api/insights/summary` (now also returns `profile_type`).

## Out of scope
- Real outbound payments (Stripe / SEPA wiring).
- Production Revolut/PSD2 eIDAS QWAC certificates.
- Daily/Weekly transfer scheduling (UI is exposed as "coming soon").
- AI insights, recurring schedules, household budgets, push notifications.

## Tests
`/app/backend/tests/test_eva_backend.py` + `/app/backend/tests/test_stub_determinism.py` + `/app/backend/tests/test_iteration4.py` — **50/50 passing**.
