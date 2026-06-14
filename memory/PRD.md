# Éva — Behavior Tax (PRD)

## Vision
Transform every purchase into a visible trade-off by attaching an automatic, customizable behavior tax that redirects money into the user's savings goals.

## MVP scope (this build)
- JWT email/password authentication (register, login, /me). Currency picked at signup (EUR / USD / GBP).
- Manual transaction entry with category + automatic tax computation.
- Per-user categories with editable tax rates (defaults seeded on signup).
- Multiple savings buckets / goals; one bucket is "active" (default) and receives the tax.
- Future Value Visualizer with adjustable years (5/10/20/30/40) and interest (3/5/7/9/12%).
- Behavioral insights: weekly chart, top categories, streak counter (days since last impulse).
- Goal Impact Analysis card on the add-transaction screen.
- Mobile UI in soft earth tones (Fraunces + DM Sans, palette per design_guidelines.json).

## Tech stack
- Frontend: Expo SDK 54, expo-router, React Native 0.81, expo-image, expo-linear-gradient, expo-font.
- Backend: FastAPI + Motor (MongoDB), JWT (python-jose), bcrypt (passlib).
- All API routes under `/api/*`. Frontend uses `EXPO_PUBLIC_BACKEND_URL` from `.env`.

## API surface
- `POST /api/auth/register` — body `{email, password, name, currency}`
- `POST /api/auth/login` — body `{email, password}`
- `GET /api/auth/me`, `PATCH /api/auth/me?currency=...&name=...&default_bucket_id=...`
- `GET/POST/PATCH/DELETE /api/categories[/:id]`
- `GET/POST/PATCH/DELETE /api/buckets[/:id]`
- `GET/POST /api/transactions`, `DELETE /api/transactions/:id`
- `GET /api/insights/summary`

## Out of scope (deferred)
- Bank/Open Banking integrations (Revolut / PSD2).
- AI-powered insights.
- Social/household features, premium tier.
- Push notifications.
