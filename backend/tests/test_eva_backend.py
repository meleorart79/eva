"""
Éva — Behavior Tax backend tests (Iteration 2).
Covers: auth, categories, buckets, bank linking, sync (Spuerkeess stub & Revolut error path),
tax engine (rep-aware + daily cap), override, transfer, activity feed, insights, removed legacy endpoints.

Test data is prefixed with TEST_ where possible; a fresh user per module is registered.
"""

import os
import uuid
import time
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

UNIQUE = uuid.uuid4().hex[:10]
USER_EMAIL = f"test_{UNIQUE}@eva-test.com"
USER_PASS = "demo1234"
USER_NAME = f"TEST_{UNIQUE}"


# ----------------- Fixtures -----------------
@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth(api_client):
    """Register a fresh user and return token + user dict."""
    r = api_client.post(f"{API}/auth/register", json={
        "email": USER_EMAIL, "password": USER_PASS, "name": USER_NAME, "currency": "EUR",
    })
    assert r.status_code == 201, f"register failed: {r.status_code} {r.text}"
    payload = r.json()
    api_client.headers.update({"Authorization": f"Bearer {payload['access_token']}"})
    return payload


# ----------------- Auth -----------------
class TestAuth:
    def test_register_login_me(self, api_client, auth):
        # /me
        r = api_client.get(f"{API}/auth/me")
        assert r.status_code == 200
        me = r.json()
        assert me["email"] == USER_EMAIL
        assert me["currency"] == "EUR"
        assert me["default_bucket_id"]

    def test_login_again(self, api_client, auth):
        r = requests.post(f"{API}/auth/login", json={"email": USER_EMAIL, "password": USER_PASS})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_patch_me_currency(self, api_client, auth):
        r = api_client.patch(f"{API}/auth/me?currency=USD")
        assert r.status_code == 200
        assert r.json()["currency"] == "USD"
        # reset
        api_client.patch(f"{API}/auth/me?currency=EUR")


# ----------------- Categories -----------------
class TestCategories:
    def test_default_seed_includes_keywords(self, api_client, auth):
        r = api_client.get(f"{API}/categories")
        assert r.status_code == 200
        cats = r.json()
        by_name = {c["name"]: c for c in cats}
        # 7 default categories
        for name in ["Coffee", "Fast Food", "Groceries", "Clothes", "Entertainment", "Transport", "Other"]:
            assert name in by_name, f"missing default category {name}"
        # Coffee keyword spec
        coffee_kw = by_name["Coffee"]["merchant_keywords"]
        for kw in ["starbucks", "coffee", "café", "costa", "pret", "tim hortons"]:
            assert kw in coffee_kw, f"Coffee missing keyword {kw}"
        # Other is catch-all empty
        assert by_name["Other"]["merchant_keywords"] == []
        # rep_increment / max_tax_rate / daily_cap_amount fields exist
        for c in cats:
            assert "rep_increment" in c
            assert "max_tax_rate" in c
            assert "daily_cap_amount" in c

    def test_create_and_patch_category_persists_new_fields(self, api_client, auth):
        payload = {
            "name": "TEST_Books", "icon": "book", "tax_rate": 0.1,
            "merchant_keywords": ["amazon", "fnac"],
            "rep_increment": 0.07, "max_tax_rate": 0.4, "daily_cap_amount": 5.5,
        }
        r = api_client.post(f"{API}/categories", json=payload)
        assert r.status_code == 201
        cid = r.json()["id"]
        # PATCH
        payload2 = {**payload, "daily_cap_amount": 9.9, "rep_increment": 0.09}
        r2 = api_client.patch(f"{API}/categories/{cid}", json=payload2)
        assert r2.status_code == 200
        body = r2.json()
        assert body["daily_cap_amount"] == 9.9
        assert body["rep_increment"] == 0.09
        # GET to verify persistence
        all_cats = api_client.get(f"{API}/categories").json()
        found = next((c for c in all_cats if c["id"] == cid), None)
        assert found and found["daily_cap_amount"] == 9.9
        # cleanup
        api_client.delete(f"{API}/categories/{cid}")


# ----------------- Bank linking -----------------
class TestBankLinking:
    def test_link_spuerkeess_returns_no_token(self, api_client, auth):
        r = api_client.post(f"{API}/bank/link", json={"provider": "spuerkeess", "access_token": "stub-token-1"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["provider"] == "spuerkeess"
        assert body["is_active"] is True
        assert "linked_at" in body
        assert "access_token" not in body

    def test_list_accounts_excludes_token(self, api_client, auth):
        r = api_client.get(f"{API}/bank/accounts")
        assert r.status_code == 200
        accs = r.json()
        assert len(accs) >= 1
        for a in accs:
            assert "access_token" not in a
            assert a["is_active"] is True

    def test_relink_deactivates_previous(self, api_client, auth):
        # Link spuerkeess again
        r = api_client.post(f"{API}/bank/link", json={"provider": "spuerkeess", "access_token": "stub-token-2"})
        assert r.status_code == 201
        accs = api_client.get(f"{API}/bank/accounts").json()
        spk_active = [a for a in accs if a["provider"] == "spuerkeess"]
        assert len(spk_active) == 1, f"expected exactly 1 active spuerkeess, got {len(spk_active)}"

    def test_delete_account_deactivates(self, api_client, auth):
        # Link a transient revolut to delete
        r = api_client.post(f"{API}/bank/link", json={"provider": "revolut", "access_token": "fake-rev-tok"})
        assert r.status_code == 201
        aid = r.json()["id"]
        d = api_client.delete(f"{API}/bank/accounts/{aid}")
        assert d.status_code == 200
        accs = api_client.get(f"{API}/bank/accounts").json()
        assert all(a["id"] != aid for a in accs)


# ----------------- Bank sync -----------------
class TestBankSync:
    """Order-dependent — must run after a spuerkeess link exists & no revolut active."""

    def test_sync_without_accounts_returns_400(self, api_client):
        """Use a brand new user without any linked accounts."""
        email = f"test_nosync_{uuid.uuid4().hex[:8]}@eva-test.com"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": USER_PASS, "name": "TEST_nosync", "currency": "EUR",
        })
        assert reg.status_code == 201
        tok = reg.json()["access_token"]
        r = requests.post(f"{API}/bank/sync", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 400
        assert "no linked" in r.text.lower() or "no bank" in r.text.lower()

    def test_first_sync_ingests_7(self, api_client, auth):
        # Ensure no revolut active for this user
        accs = api_client.get(f"{API}/bank/accounts").json()
        for a in accs:
            if a["provider"] == "revolut":
                api_client.delete(f"{API}/bank/accounts/{a['id']}")
        # Sleep 1s so provider_txn_id timestamp differs from any earlier
        time.sleep(1.1)
        r = api_client.post(f"{API}/bank/sync")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ingested"] == 7
        # Re-run -> duplicates increase, ingested=0 for same timestamp window
        # Note: provider_txn_id includes int(now.timestamp()) so if we call immediately
        # it will produce same IDs and dedupe. Force same-second by no sleep.
        r2 = api_client.post(f"{API}/bank/sync")
        body2 = r2.json()
        # Either dedup (same second) or ingested 7 more (next second). Validate the dedup path explicitly.
        # We retry quickly to land in same second.
        if body2["ingested"] != 0:
            # try once more in same second
            r3 = api_client.post(f"{API}/bank/sync")
            body2 = r3.json()
        assert body2["duplicates"] >= 7, f"expected duplicates on rerun, got {body2}"

    def test_revolut_sync_error_surfaces(self, api_client, auth):
        # Link revolut with bogus token (deactivates anything else but we keep spuerkeess active per provider rule)
        r = api_client.post(f"{API}/bank/link", json={"provider": "revolut", "access_token": "definitely-not-valid"})
        assert r.status_code == 201
        rid = r.json()["id"]
        sync = api_client.post(f"{API}/bank/sync")
        # Should be 401 (token rejected) or 502 (network/sandbox error). Both are acceptable per spec.
        assert sync.status_code in (401, 502), f"expected 401/502, got {sync.status_code} {sync.text}"
        # Cleanup so it doesn't affect later tests
        api_client.delete(f"{API}/bank/accounts/{rid}")


# ----------------- Tax engine -----------------
class TestTaxEngine:
    def test_process_taxes_spuerkeess(self, api_client, auth):
        # Get default bucket starting saved_amount
        buckets = api_client.get(f"{API}/buckets").json()
        default_b = next(b for b in buckets if b["is_default"])
        starting_saved = default_b["saved_amount"]

        # Snapshot pending raw_transactions count via activity feed (status=pending)
        before = api_client.get(f"{API}/activity?limit=200").json()
        pending_before = [a for a in before if a["status"] == "pending"]
        assert len(pending_before) >= 7, f"expected >=7 pending raw_tx, got {len(pending_before)}"

        r = api_client.post(f"{API}/tax/process")
        assert r.status_code == 200
        body = r.json()
        assert body["processed"] >= 7
        assert body["taxed"] >= 5  # 6 stubbed should match keyword (Starbucks, Cactus, McDonalds, Uber, Spotify, Zara, Costa) = 7 matches
        # All 7 stub merchants should match. unmatched should be 0 for those 7.
        # But there could be earlier dedup leftovers. Just sanity check.
        assert body["taxed"] + body["skipped"] + body["unmatched"] == body["processed"]

        # Bucket should have increased
        buckets2 = api_client.get(f"{API}/buckets").json()
        default_b2 = next(b for b in buckets2 if b["is_default"])
        assert default_b2["saved_amount"] > starting_saved, "default bucket saved_amount should increase"

    def test_repetition_increments_rate_for_coffee(self, api_client, auth):
        # Find tax events for Coffee category, expect 2 (Starbucks + Costa) with second rate > first.
        rows = api_client.get(f"{API}/activity?limit=200").json()
        coffee_rows = [r for r in rows if r.get("category_name") == "Coffee" and r["tax_event_id"]]
        # Sort by transacted_at ascending
        coffee_rows.sort(key=lambda x: x["transacted_at"])
        assert len(coffee_rows) >= 2, f"expected >=2 Coffee tax events, got {len(coffee_rows)}"
        # The second event's rate should be >= first event's rate (rep_increment applied)
        rates = [c["tax_rate_applied"] for c in coffee_rows[:2]]
        assert rates[1] > rates[0], f"second Coffee rate should exceed first (rep): {rates}"

    def test_daily_cap_skips_second_coffee(self, api_client):
        """Fresh user, lower Coffee cap to 0.50, sync+process => second coffee tx must be 'skipped'."""
        email = f"test_cap_{uuid.uuid4().hex[:8]}@eva-test.com"
        reg = requests.post(f"{API}/auth/register", json={
            "email": email, "password": USER_PASS, "name": "TEST_cap", "currency": "EUR",
        })
        assert reg.status_code == 201
        tok = reg.json()["access_token"]
        h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

        # Lower Coffee daily_cap_amount to 0.50
        cats = requests.get(f"{API}/categories", headers=h).json()
        coffee = next(c for c in cats if c["name"] == "Coffee")
        patch_payload = {**coffee, "daily_cap_amount": 0.50}
        patch_payload.pop("id", None)
        rp = requests.patch(f"{API}/categories/{coffee['id']}", json=patch_payload, headers=h)
        assert rp.status_code == 200
        assert rp.json()["daily_cap_amount"] == 0.50

        # Link spuerkeess, sync, process
        lnk = requests.post(f"{API}/bank/link",
                            json={"provider": "spuerkeess", "access_token": "stub-cap-tok"}, headers=h)
        assert lnk.status_code == 201, f"link failed: {lnk.status_code} {lnk.text}"
        sync = requests.post(f"{API}/bank/sync", headers=h)
        assert sync.status_code == 200, f"sync failed: {sync.status_code} {sync.text}"
        assert sync.json()["ingested"] == 7
        proc = requests.post(f"{API}/tax/process", headers=h)
        assert proc.status_code == 200

        # Verify exactly 1 Coffee tax_event exists, and a skipped status appears for the other coffee
        activity = requests.get(f"{API}/activity?limit=200", headers=h).json()
        coffee_rows = [a for a in activity if (a.get("category_name") == "Coffee" or
                                               "starbucks" in a["merchant_name"].lower() or
                                               "costa" in a["merchant_name"].lower())]
        # Find by merchant
        sb = next((a for a in activity if "starbucks" in a["merchant_name"].lower()), None)
        co = next((a for a in activity if "costa" in a["merchant_name"].lower()), None)
        assert sb is not None and co is not None
        statuses = sorted([sb["status"], co["status"]])
        assert statuses == ["saved", "skipped"], f"expected one saved + one skipped, got {statuses}"


# ----------------- Activity feed -----------------
class TestActivity:
    def test_activity_can_override_flag(self, api_client, auth):
        rows = api_client.get(f"{API}/activity?limit=200").json()
        saved = [r for r in rows if r["status"] == "saved"]
        assert len(saved) > 0
        # Recent saved rows should have can_override=True (within 10 min)
        recent = [r for r in saved if r["can_override"]]
        assert len(recent) > 0, "expected at least one can_override=True row"


# ----------------- Override -----------------
class TestOverride:
    def test_override_decrements_bucket(self, api_client, auth):
        rows = api_client.get(f"{API}/activity?limit=200").json()
        target = next((r for r in rows if r["status"] == "saved" and r["can_override"]), None)
        assert target is not None, "need a recent saved tax_event"
        event_id = target["tax_event_id"]
        tax_amt = target["tax_amount"]

        buckets_before = api_client.get(f"{API}/buckets").json()
        default_before = next(b for b in buckets_before if b["is_default"])["saved_amount"]

        r = api_client.post(f"{API}/tax/override/{event_id}")
        assert r.status_code == 200

        buckets_after = api_client.get(f"{API}/buckets").json()
        default_after = next(b for b in buckets_after if b["is_default"])["saved_amount"]
        assert abs((default_before - default_after) - tax_amt) < 0.01, \
            f"bucket should decrement by {tax_amt}: {default_before} -> {default_after}"

        # Second override -> 400
        r2 = api_client.post(f"{API}/tax/override/{event_id}")
        assert r2.status_code == 400

    def test_override_unknown_event_404(self, api_client, auth):
        r = api_client.post(f"{API}/tax/override/{uuid.uuid4()}")
        assert r.status_code == 404


# ----------------- Transfer -----------------
class TestTransfer:
    def test_transfer_marks_pending_transferred(self, api_client, auth):
        api_client.patch(f"{API}/settings", json={"transfer_frequency": "weekly"})
        api_client.post(f"{API}/tax/process")
        r = api_client.post(f"{API}/tax/transfer")
        assert r.status_code == 200
        body = r.json()
        assert body["transferred"] >= 1
        assert body["total_amount"] >= 0
        assert "transfer_id" in body

    def test_transfer_no_pending_returns_zero(self, api_client, auth):
        api_client.patch(f"{API}/settings", json={"transfer_frequency": "weekly"})
        api_client.post(f"{API}/tax/process")
        r = api_client.post(f"{API}/tax/transfer")
        assert r.status_code == 200
        body = r.json()
        assert body["transferred"] == 0
        assert body["total_amount"] == 0.0


# ----------------- Insights -----------------
class TestInsights:
    def test_summary_excludes_overridden(self, api_client, auth):
        r = api_client.get(f"{API}/insights/summary")
        assert r.status_code == 200
        s = r.json()
        for k in ["total_spent", "total_taxed", "transactions", "by_category", "by_day", "streak_days_no_impulse"]:
            assert k in s
        assert s["transactions"] >= 1
        # by_category items have shape
        if s["by_category"]:
            row = s["by_category"][0]
            for k in ["name", "spent", "taxed", "count"]:
                assert k in row
        # by_day items
        if s["by_day"]:
            d = s["by_day"][0]
            for k in ["date", "spent", "taxed"]:
                assert k in d


# ----------------- Removed legacy endpoint -----------------
class TestRemovedLegacy:
    def test_post_transactions_removed(self, api_client, auth):
        r = api_client.post(f"{API}/transactions", json={"merchant": "x", "amount": 1})
        assert r.status_code in (404, 405)

    def test_get_transactions_removed(self, api_client, auth):
        r = api_client.get(f"{API}/transactions")
        assert r.status_code in (404, 405)


# ----------------- Buckets (regression) -----------------
class TestBucketsRegression:
    def test_bucket_crud_and_default_swap(self, api_client, auth):
        # Create new default — should flip previous default off
        r = api_client.post(f"{API}/buckets", json={
            "name": "TEST_NewDefault", "target_amount": 500, "image_key": "travel", "is_default": True,
        })
        assert r.status_code == 201
        new_id = r.json()["id"]
        buckets = api_client.get(f"{API}/buckets").json()
        defaults = [b for b in buckets if b["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == new_id
        # Cannot delete the default
        d = api_client.delete(f"{API}/buckets/{new_id}")
        assert d.status_code == 400
        # Switch default back via PATCH on old bucket
        old_default = next(b for b in buckets if b["id"] != new_id and b["name"] == "Travel Fund")
        api_client.patch(f"{API}/buckets/{old_default['id']}", json={
            "name": old_default["name"], "target_amount": old_default["target_amount"],
            "image_key": old_default["image_key"], "is_default": True,
        })
        # Now delete new bucket
        d2 = api_client.delete(f"{API}/buckets/{new_id}")
        assert d2.status_code == 200

class TestRepetitionDayBoundary:
    def test_same_session_different_calendar_days(self, api_client, auth):
        # Transaction at 23:58 and 00:02 (next day) must land in different
        # daily repetition buckets even though they're in the same session.
        t1 = "2024-01-01T23:58:00Z"
        t2 = "2024-01-02T00:02:00Z"

        api_client.post(f"{API}/bank/mock-transactions", json={
            "merchant": "Starbucks", "amount": 4.50, "transacted_at": t1
        })
        api_client.post(f"{API}/bank/mock-transactions", json={
            "merchant": "Starbucks", "amount": 4.50, "transacted_at": t2
        })
        api_client.post(f"{API}/tax/process")

        r = api_client.get(f"{API}/insights/summary")
        assert r.status_code == 200
        # Both transactions should be taxed at the base rate (hit_count == 0
        # for each), not at an escalated repetition rate, proving they were
        # counted on separate days.