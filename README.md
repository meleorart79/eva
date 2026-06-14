# Eva - Behavior Tax

Eva is a full-stack mobile app that turns everyday spending into automatic saving.

The product idea is simple: a user connects a bank account, Eva watches future
transactions, applies a configurable "behavior tax" to eligible expenses, and
routes the tax amount toward a savings destination. The app is designed around a
Revolut-first flow, with a deterministic Spuerkeess stub for local and test
work.

This repository contains:

- A FastAPI backend with MongoDB persistence.
- An Expo / React Native frontend.
- Bank linking, transaction sync, behavior categories, savings destinations,
  source-aware simulated transfers, scheduler support, monthly reports, and
  backend regression tests.

## Table Of Contents

- [Product Concept](#product-concept)
- [Current Status](#current-status)
- [Repository Structure](#repository-structure)
- [Architecture](#architecture)
- [Core User Flow](#core-user-flow)
- [Domain Model](#domain-model)
- [Behavior Tax Engine](#behavior-tax-engine)
- [Transfers And Destinations](#transfers-and-destinations)
- [Revolut Integration](#revolut-integration)
- [Frontend Screens](#frontend-screens)
- [Backend API](#backend-api)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Running Locally](#running-locally)
- [Testing](#testing)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Development Notes](#development-notes)

## Product Concept

Eva is a behavior-tax assistant.

After the user connects a supported bank account, Eva should only consider
transactions that happen after the connection is created. It should never tax old
purchases. For each new eligible expense, Eva:

1. Syncs the transaction from the connected provider.
2. Confirms the transaction happened after the account was connected.
3. Detects the source account, card, pocket, or balance used for the expense.
4. Matches the merchant to a behavior category.
5. Calculates a tax percentage.
6. Creates a tax event.
7. Routes the tax amount from the transaction source to the user's chosen
   savings destination.
8. Shows the transaction, tax amount, source, destination, and transfer status
   in the app.

In this codebase, real outbound money movement is not production wired yet.
Transfer execution is simulated and recorded with provider-like references.

## Current Status

Implemented:

- Email/password authentication with JWT.
- User profile and currency selection.
- Default behavior categories.
- Editable category tax rates and merchant keywords.
- Bank account linking:
  - Revolut sandbox OAuth consent flow.
  - Revolut direct-token compatibility path for tests.
  - Spuerkeess deterministic stub provider.
- No-retroactive sync rule using `connected_at`.
- Source-aware raw transactions.
- Savings destinations:
  - `external_iban`
  - `revolut_pocket`
- Destination currency validation against the user/bank currency.
- Behavior-tax processing with:
  - category matching,
  - repetition-aware tax rates,
  - max rate caps,
  - daily tax caps,
  - profile multipliers,
  - pause-all-taxes support,
  - review state for missing source, missing destination, or currency mismatch.
- Transfer modes:
  - instant,
  - daily,
  - weekly.
- Grouped simulated transfers by source account and destination.
- Manual scheduler trigger.
- Monthly report JSON and CSV export.
- Activity feed with override support.
- Frontend screens for dashboard, goals, insights, profile, settings,
  destinations, bank linking, category management, and monthly report.

Partially implemented or simulated:

- Revolut sandbox account linking is present, but production Revolut payment
  initiation is not implemented.
- Savings destinations are stored and validated, but transfers are simulated.
- Scheduler loop exists in-process; production scheduling would need a robust
  worker or job system.

## Repository Structure

```text
.
|-- backend/
|   |-- server.py                 # FastAPI app, domain logic, API routes
|   |-- requirements.txt          # Python dependencies
|   `-- tests/                    # Backend pytest regression tests
|
|-- frontend/
|   |-- app/                      # Expo Router screens
|   |-- src/
|   |   |-- api.ts                # Typed frontend API client
|   |   |-- auth.tsx              # Auth/session provider
|   |   |-- components/           # Shared UI components
|   |   |-- hooks/                # Font/icon hooks
|   |   |-- theme.ts              # Design tokens
|   |   `-- utils/storage/        # Secure/local storage abstraction
|   |-- assets/                   # Images and fonts
|   |-- package.json
|   `-- tsconfig.json
|
|-- memory/
|   `-- PRD.md                    # Product notes from earlier iteration
|
|-- test_reports/                 # Test result artifacts
|-- tests/                        # Root test package marker
|-- design_guidelines.json
|-- eva_structure.py
`-- README.md
```

## Architecture

Eva uses a straightforward client/server architecture:

```text
Expo mobile app
    |
    | HTTPS / JSON
    v
FastAPI backend
    |
    | Motor async driver
    v
MongoDB
    |
    | Provider API calls / stubs
    v
Revolut sandbox or Spuerkeess stub
```

### Backend

The backend is a single FastAPI app in `backend/server.py`. It owns:

- auth,
- user defaults,
- categories,
- savings goals,
- savings destinations,
- bank linking,
- transaction sync,
- tax processing,
- transfer simulation,
- scheduler execution,
- activity feed,
- insights,
- monthly reports.

The app exposes all routes under `/api`.

### Frontend

The frontend is an Expo app using Expo Router. It talks to the backend through
`frontend/src/api.ts`, which wraps fetch calls and injects the JWT bearer token
from secure storage.

The frontend expects `EXPO_PUBLIC_BACKEND_URL` to point at the backend origin.

## Core User Flow

1. User registers with email, password, name, and currency.
2. Backend seeds:
   - default behavior categories,
   - a default savings goal,
   - a default Revolut-style savings destination.
3. User links a bank account.
4. Backend stores `linked_at` and `connected_at`.
5. User syncs transactions.
6. Backend ignores any transaction at or before `connected_at`.
7. Backend stores only new transactions with source metadata.
8. User or app triggers tax processing.
9. Backend creates tax events for matched purchases.
10. Backend either:
    - transfers immediately if `transfer_frequency = instant`,
    - leaves events pending for daily/weekly scheduler,
    - or marks events as `requires_review`.
11. User sees activity, transfer status, insights, and monthly reports.

## Domain Model

The implementation uses MongoDB collections. Documents are stored with string
UUID-style `id` fields instead of MongoDB ObjectId as the public identifier.

### `users`

Stores account and settings data.

Important fields:

- `id`
- `email`
- `password_hash`
- `name`
- `currency`
- `default_bucket_id`
- `profile_type`
- `transfer_frequency`
- `pause_all_taxes`
- `transfer_last_run_at`
- `created_at`

Supported currencies at registration are `EUR`, `USD`, and `GBP`.

### `categories`

Behavior categories used for merchant matching and tax calculation.

Important fields:

- `id`
- `user_id`
- `name`
- `icon`
- `tax_rate`
- `merchant_keywords`
- `rep_increment`
- `max_tax_rate`
- `daily_cap_amount`

Default categories:

- Coffee
- Fast Food
- Groceries
- Clothes
- Entertainment
- Transport
- Other
- Ethical Penalty

### `buckets`

Savings-goal UI objects. These represent the visible "goal" progress inside
the app.

Important fields:

- `id`
- `user_id`
- `name`
- `target_amount`
- `saved_amount`
- `image_key`
- `is_default`
- `created_at`

### `savings_destinations`

Payment-routing destinations. These are distinct from visual savings goals.

Important fields:

- `id`
- `user_id`
- `type`
- `label`
- `identifier`
- `currency`
- `is_default`
- `is_active`
- `created_at`

Supported types:

- `external_iban`
- `revolut_pocket`

### `linked_accounts`

Connected bank-provider accounts.

Important fields:

- `id`
- `user_id`
- `provider`
- `access_token`
- `refresh_token`
- `token_expires_at`
- `is_active`
- `oauth_state`
- `redirect_uri`
- `linked_at`
- `connected_at`
- `primary_currency`

Providers:

- `revolut`
- `spuerkeess`

### `raw_transactions`

Provider transactions after ingestion and before/after tax processing.

Important fields:

- `id`
- `user_id`
- `account_id`
- `provider_txn_id`
- `merchant_name`
- `amount`
- `currency`
- `transacted_at`
- `ingested_at`
- `matched_category_id`
- `status`
- `source_account_id`
- `source_label`
- `source_type`
- `source_currency`

Status examples:

- `pending`
- `taxed`
- `skipped`
- `unmatched`

### `daily_repetition_counters`

Tracks how many times a category has been hit on a specific day.

Important fields:

- `id`
- `user_id`
- `category_id`
- `counter_date`
- `hit_count`

### `tax_events`

Tax calculations generated from raw transactions.

Important fields:

- `id`
- `user_id`
- `raw_txn_id`
- `category_id`
- `category_name`
- `bucket_id`
- `original_amount`
- `tax_rate_applied`
- `tax_amount`
- `repetition_number`
- `status`
- `override_reason`
- `profile_applied`
- `transacted_at`
- `created_at`
- `source_account_id`
- `source_label`
- `source_type`
- `source_currency`
- `destination_id`
- `destination_label`
- `destination_currency`
- `transfer_status`
- `transfer_id`
- `transfer_provider_ref`
- `requires_review`
- `review_reason`

Tax event statuses:

- `pending`
- `transferred`
- `overridden`

Transfer statuses:

- `pending`
- `executed`
- `failed`
- `requires_review`

Review reasons:

- `unknown_source`
- `no_destination`
- `currency_mismatch`

### `tax_transfers`

Grouped transfer records. Each transfer may contain several tax events when they
share the same source account and destination.

Important fields:

- `id`
- `user_id`
- `source_account_id`
- `source_label`
- `destination_id`
- `destination_label`
- `destination_currency`
- `tax_event_ids`
- `total_amount`
- `status`
- `provider_ref`
- `executed_at`
- `trigger`

Current transfer status is `simulated` because provider payment execution is not
production wired.

Transfer triggers include:

- `instant`
- `manual`
- `savings_beast_auto`
- `scheduler_daily`
- `scheduler_weekly`
- `scheduler_daily_manual`
- `scheduler_weekly_manual`
- `scheduler_manual`

## Behavior Tax Engine

The tax engine is implemented by `POST /api/tax/process`.

### Processing Rules

For each pending raw transaction:

1. Match the merchant against category keywords.
2. If no category matches, mark the transaction `unmatched`.
3. Load the category repetition counter for that transaction day.
4. Compute the repetition-aware rate:

```text
rep_rate = min(max_tax_rate, tax_rate + hit_count * rep_increment)
```

5. Apply the selected behavior profile multiplier.
6. Enforce the category daily cap.
7. Resolve transaction source metadata.
8. Resolve the active default savings destination.
9. Create a tax event.
10. Increment the repetition counter.
11. Increment the default bucket's visible saved amount.
12. Mark the raw transaction as taxed, skipped, or unmatched.
13. Execute transfers if the user's transfer mode calls for it.

### Behavior Profiles

Profiles are stored on the user document as `profile_type`.

| Profile | Behavior |
| --- | --- |
| `balanced` | Uses configured category rates. |
| `aggressive` | Multiplies effective rates by 1.5, bounded by category max. |
| `ethical` | Multiplies selected categories by 1.4. |
| `mindful` | Halves effective rates. |
| `savings_beast` | Uses aggressive behavior and can auto-transfer above the configured trigger. |

### Pause Mode

If `pause_all_taxes` is true, `POST /api/tax/process` short-circuits and returns:

```json
{ "paused": true }
```

### Override Window

Users can override a tax event for 10 minutes after creation.

`POST /api/tax/override/{event_id}`:

- marks the event as `overridden`,
- stores `override_reason = intentional`,
- subtracts the tax amount from the associated bucket's saved amount.

## Transfers And Destinations

Eva distinguishes between a visual savings goal and an actual destination:

- `buckets` are app-level savings goals.
- `savings_destinations` are routing destinations for tax transfers.

The default destination is created on registration:

```text
type: revolut_pocket
label: Default Savings Pocket
currency: user's selected currency
```

### Currency Rule

Destination currency must match the user's currency or an active linked account
currency. The current tests verify that a EUR user can create EUR destinations
and rejects USD when no linked USD account exists.

### Source-Aware Transfers

Eva records the source used for each purchase:

- source account ID,
- source label,
- source type,
- source currency.

When executing transfers, Eva groups pending eligible tax events by:

```text
(source_account_id, destination_id)
```

It then creates one simulated transfer per group.

### Requires Review

A tax event is marked `requires_review` when Eva cannot safely transfer it.

Current review cases:

- unknown transaction source,
- no active savings destination,
- source/destination currency mismatch.

Events requiring review are excluded from transfer execution.

## Revolut Integration

The Revolut integration is sandbox-oriented.

### OAuth Flow

`POST /api/bank/link` with:

```json
{ "provider": "revolut" }
```

returns a `consent_url`. The frontend opens it using Expo WebBrowser. Revolut
redirects to:

```text
/api/bank/revolut/callback
```

The callback exchanges the authorization code for tokens, stores refresh token
metadata, marks the linked account active, sets `connected_at`, and redirects
back to the app through the `eva://bank-callback` deep link.

### Direct Token Compatibility

For tests and legacy flows, `POST /api/bank/link` also accepts:

```json
{
  "provider": "revolut",
  "access_token": "token"
}
```

### No-Retroactive Rule

Every linked account receives a `connected_at` timestamp. During sync:

```text
if transaction.transacted_at <= linked_account.connected_at:
    skip transaction
```

This is central to the product. Eva should only tax spending after the user has
connected the account and opted into the behavior.

### Spuerkeess Stub

The `spuerkeess` provider is deterministic and exists for local development and
tests. It emits realistic sample expenses after the connection timestamp and
includes two source accounts:

- `spk_main`
- `spk_card_1234`

This lets the transfer grouping logic be tested without a real bank.

## Frontend Screens

The Expo app uses file-based routing under `frontend/app`.

Important screens:

- `app/onboarding.tsx` - landing/onboarding screen.
- `app/(auth)/register.tsx` - registration.
- `app/(auth)/login.tsx` - login.
- `app/(tabs)/index.tsx` - dashboard and activity feed.
- `app/(tabs)/buckets.tsx` - savings goals.
- `app/(tabs)/insights.tsx` - insights and projections.
- `app/(tabs)/profile.tsx` - profile, currency, links.
- `app/(tabs)/settings.tsx` - profile modes, transfer timing, banks, danger zone.
- `app/link-bank.tsx` - Revolut/Spuerkeess linking.
- `app/categories.tsx` - behavior category management.
- `app/destinations.tsx` - savings destination management.
- `app/monthly-resume.tsx` - monthly summary and CSV export.
- `app/bucket-new.tsx` - create savings goal.

## Backend API

All routes are prefixed with `/api`.

### Health

#### `GET /api/`

Returns basic app status.

```json
{
  "app": "Eva - Behavior Tax",
  "status": "ok"
}
```

### Auth

#### `POST /api/auth/register`

Body:

```json
{
  "email": "user@example.com",
  "password": "demo1234",
  "name": "Jane",
  "currency": "EUR"
}
```

Creates the user, seeds defaults, and returns a JWT.

#### `POST /api/auth/login`

Body:

```json
{
  "email": "user@example.com",
  "password": "demo1234"
}
```

#### `GET /api/auth/me`

Returns current user.

#### `PATCH /api/auth/me`

Query parameters:

- `currency`
- `name`
- `default_bucket_id`

### Settings

#### `GET /api/settings`

Returns:

```json
{
  "profile_type": "balanced",
  "transfer_frequency": "instant",
  "pause_all_taxes": false,
  "transfer_last_run_at": null
}
```

#### `PATCH /api/settings`

Body may include:

```json
{
  "profile_type": "mindful",
  "transfer_frequency": "daily",
  "pause_all_taxes": false
}
```

### Categories

#### `GET /api/categories`

Lists behavior categories.

#### `POST /api/categories`

Body:

```json
{
  "name": "Books",
  "icon": "book",
  "tax_rate": 0.1,
  "merchant_keywords": ["bookstore", "kindle"],
  "rep_increment": 0.03,
  "max_tax_rate": 0.3,
  "daily_cap_amount": 8
}
```

#### `PATCH /api/categories/{cid}`

Updates a category.

#### `DELETE /api/categories/{cid}`

Deletes a category.

### Buckets

#### `GET /api/buckets`

Lists savings goals.

#### `POST /api/buckets`

Body:

```json
{
  "name": "Emergency Fund",
  "target_amount": 3000,
  "image_key": "travel",
  "is_default": true
}
```

#### `PATCH /api/buckets/{bid}`

Updates a savings goal.

#### `DELETE /api/buckets/{bid}`

Deletes a savings goal. The default bucket cannot be deleted.

### Savings Destinations

#### `GET /api/destinations`

Lists active destinations.

#### `POST /api/destinations`

Body:

```json
{
  "type": "external_iban",
  "label": "Savings Account",
  "identifier": "LU000000000",
  "currency": "EUR",
  "is_default": true
}
```

#### `PATCH /api/destinations/{did}`

Updates a destination. If `is_default` is true, other destinations are unset.

#### `DELETE /api/destinations/{did}`

Soft-deletes a destination by marking it inactive. If the deleted destination
was default, another active destination is promoted when possible.

### Bank

#### `POST /api/bank/link`

Revolut OAuth:

```json
{ "provider": "revolut" }
```

Spuerkeess stub:

```json
{
  "provider": "spuerkeess",
  "access_token": "stub"
}
```

Returns a linked account. Revolut OAuth returns a `consent_url`.

#### `GET /api/bank/accounts`

Lists active linked accounts. Tokens are not returned.

#### `DELETE /api/bank/accounts/{aid}`

Deactivates a linked account.

#### `GET /api/bank/revolut/callback`

OAuth callback route used by Revolut.

#### `POST /api/bank/sync`

Syncs transactions from all active linked accounts.

Response includes:

```json
{
  "ingested": 7,
  "duplicates": 0,
  "skipped_retroactive": 0,
  "accounts": 1
}
```

### Tax

#### `POST /api/tax/process`

Processes pending raw transactions.

Typical response:

```json
{
  "processed": 7,
  "taxed": 7,
  "skipped": 0,
  "unmatched": 0,
  "requires_review": 0,
  "instant_transfer": {
    "transferred": 7,
    "total_amount": 12.34,
    "transfers": []
  }
}
```

#### `POST /api/tax/override/{event_id}`

Overrides a recent tax event.

#### `POST /api/tax/transfer`

Manual transfer trigger. Groups eligible pending tax events and simulates
transfers.

### Scheduler

#### `POST /api/scheduler/run`

Manually runs the scheduler once for the current user. Useful for testing daily
or weekly transfer behavior.

### Activity

#### `GET /api/activity?limit=100`

Returns recent transaction/activity rows with tax and transfer metadata.

### Insights

#### `GET /api/insights/summary`

Returns totals, category aggregation, day aggregation, streak estimate, and the
current profile.

### Reports

#### `GET /api/reports/monthly?year=2026&month=6`

Returns monthly report JSON:

- totals,
- by category,
- by profile,
- by destination,
- by transfer status,
- event rows.

#### `GET /api/reports/monthly/export.csv?year=2026&month=6`

Exports the same monthly report as CSV.

## Setup

### Prerequisites

- Python 3.11+ recommended.
- Node.js compatible with Expo SDK 54.
- Yarn 1.x.
- MongoDB running locally or accessible through `MONGO_URL`.
- Expo CLI through `yarn expo` / `npx expo`.

### Backend Installation

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Frontend Installation

From the repository root:

```powershell
cd frontend
yarn install
```

The frontend package has an install guard and declares Yarn as the package
manager.

## Environment Variables

### Backend `.env`

Create `backend/.env`:

```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=eva
JWT_SECRET=replace-this-in-real-environments

# Optional Revolut sandbox values
REVOLUT_CLIENT_ID=05f4b015-b95a-423b-a7c8-c4e33c17b97d
REVOLUT_REDIRECT_URI=
```

Required:

- `MONGO_URL`
- `DB_NAME`

Optional:

- `JWT_SECRET`
- `REVOLUT_CLIENT_ID`
- `REVOLUT_REDIRECT_URI`

If `REVOLUT_REDIRECT_URI` is omitted, the backend builds one from the incoming
request base URL:

```text
{base_url}/api/bank/revolut/callback
```

### Frontend `.env`

Create `frontend/.env`:

```env
EXPO_PUBLIC_BACKEND_URL=http://localhost:8001
```

For a physical device, use a LAN-reachable backend URL instead of `localhost`.

## Running Locally

### Start MongoDB

Use your local MongoDB service, Docker, or a hosted MongoDB connection.

Example Docker command:

```powershell
docker run --name eva-mongo -p 27017:27017 -d mongo:7
```

### Start Backend

From `backend`:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Backend health check:

```text
http://localhost:8001/api/
```

### Start Frontend

From `frontend`:

```powershell
yarn start
```

For web:

```powershell
yarn web
```

For Android:

```powershell
yarn android
```

For iOS:

```powershell
yarn ios
```

## Testing

Backend tests are written with pytest and use HTTP requests against a running
backend.

### Test Environment

Set the backend URL for tests:

```powershell
$env:EXPO_PUBLIC_BACKEND_URL="http://localhost:8001"
$env:MONGO_URL="mongodb://localhost:27017"
$env:DB_NAME="eva_test"
```

Then start the backend with the same `MONGO_URL` and `DB_NAME`.

### Run Backend Tests

From the repository root:

```powershell
pytest backend/tests
```

Individual suites:

```powershell
pytest backend/tests/test_eva_backend.py
pytest backend/tests/test_stub_determinism.py
pytest backend/tests/test_iteration4.py
pytest backend/tests/test_iteration5.py
```

### Current Test Notes

The latest recorded iteration-5 report says:

- 20/20 iteration-5 tests passed.
- 68/70 total backend tests passed.
- The two older failures are assertion drift from newer behavior:
  - instant transfers can empty pending events before legacy manual transfer
    assertions run,
  - settings now include `transfer_last_run_at`.

See `test_reports/iteration_5.json` for details.

### Frontend Checks

Run lint from `frontend`:

```powershell
yarn lint
```

The repository does not currently define a frontend unit-test command.

## Known Limitations

- Real outbound payment execution is not implemented.
- Tax transfers are simulated with `sim_...` provider references.
- Revolut integration targets sandbox/open-banking style APIs.
- Production Revolut payment initiation, vault/pocket movement, consent renewal,
  and PSD2 compliance work remain outside the current implementation.
- The scheduler runs in-process. Production should use a durable job runner.
- The backend is currently concentrated in one large `server.py` file.
- Some older tests encode behavior from earlier iterations and need assertion
  updates.
- The Spuerkeess stub generates transactions relative to `connected_at`, which
  is excellent for no-retroactive happy-path testing but less useful for tests
  that manually shift `connected_at` forward.
- Category matching is keyword-based and intentionally simple.
- The Ethical Penalty category is checked first, so certain merchants may route
  there even outside the ethical profile.

## Roadmap

High-priority product work:

- Replace simulated transfers with real Revolut-supported money movement.
- Model Revolut accounts, cards, pockets, vaults, and balances more explicitly.
- Confirm whether transfers can originate from the exact source used for a card
  transaction through the available Revolut APIs.
- Add robust handling when exact source cannot be determined.
- Strengthen destination validation for real IBAN and Revolut pocket references.
- Make currency behavior location-aware and bank-aware.
- Add webhook or polling strategy for near-real-time transaction detection.
- Add production-grade scheduler/worker infrastructure.

Backend engineering:

- Split `backend/server.py` into modules:
  - auth,
  - users/settings,
  - categories,
  - destinations,
  - bank providers,
  - tax engine,
  - transfers,
  - scheduler,
  - reports.
- Add indexes for common MongoDB lookups.
- Add migration/backfill scripts for evolving document shapes.
- Add stricter schemas for persisted documents.
- Improve monthly report query efficiency.
- Track scheduler task cancellation on shutdown.

Frontend product:

- Make source account and destination details more prominent in activity.
- Add review resolution flows.
- Add stronger empty, loading, and failure states for bank sync and transfers.
- Add destination validation feedback.
- Add clearer copy explaining no retroactive taxation.

Testing:

- Update old tests for instant-transfer behavior and expanded settings shape.
- Add frontend smoke tests.
- Add contract tests for API response shapes.
- Add provider parser tests for Revolut payload variations.

## Development Notes

### API Client

Frontend API calls live in:

```text
frontend/src/api.ts
```

This file defines the TypeScript types consumed by screens and centralizes auth
header injection.

### Auth Storage

JWT storage is abstracted under:

```text
frontend/src/utils/storage/
```

Native builds use secure storage where available; web uses a compatible storage
path.

### Test IDs

Screens use `testID` props for automated UI targeting. Shared constants live
under:

```text
frontend/constants/testIds/
```

### Deep Link

The app uses:

```text
eva://bank-callback
```

for returning from the Revolut OAuth browser session.

### Safety Principle

The most important product safety rule is:

```text
Never tax transactions that happened before the account was connected.
```

Any future provider integration, sync optimization, webhook handler, or backfill
job should preserve that invariant.
