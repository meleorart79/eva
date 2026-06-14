"""
Focused regression test for iteration 3:
- Spuerkeess stub must be deterministic: two syncs within the same second
  yield ingested=0 / duplicates=7 on the second run.
- Daily-cap logic verifies once more in isolation with a fresh user.
"""
import os
import uuid
import time
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"


def _fresh_user(suffix: str):
    email = f"test_{suffix}_{uuid.uuid4().hex[:8]}@eva-test.com"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "demo1234",
        "name": f"TEST_{suffix}", "currency": "EUR",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "Content-Type": "application/json"}


def test_spuerkeess_stub_deterministic_same_second():
    h = _fresh_user("det")
    lnk = requests.post(f"{API}/bank/link",
                       json={"provider": "spuerkeess", "access_token": "det-tok"},
                       headers=h)
    assert lnk.status_code == 201

    # Sleep briefly so we don't collide with any prior test's epoch-second.
    time.sleep(1.1)

    # First sync: must ingest 7, duplicates 0
    s1 = requests.post(f"{API}/bank/sync", headers=h)
    assert s1.status_code == 200, s1.text
    b1 = s1.json()
    assert b1["ingested"] == 7, f"first sync should ingest 7, got {b1}"
    assert b1["duplicates"] == 0, f"first sync should have 0 duplicates, got {b1}"

    # Second sync immediately (same second). Determinism means provider_txn_id
    # collides exactly -> all 7 are duplicates.
    # We retry up to 3 times to land in the same wall-clock second.
    last = None
    for _ in range(3):
        s2 = requests.post(f"{API}/bank/sync", headers=h)
        assert s2.status_code == 200
        b2 = s2.json()
        last = b2
        if b2["ingested"] == 0 and b2["duplicates"] == 7:
            break
    assert last["ingested"] == 0, f"same-second resync should ingest 0, got {last}"
    assert last["duplicates"] == 7, f"same-second resync should dedupe 7, got {last}"


def test_daily_cap_only_first_coffee_taxed():
    h = _fresh_user("cap2")
    # Lower Coffee daily cap to 0.50 EUR.
    cats = requests.get(f"{API}/categories", headers=h).json()
    coffee = next(c for c in cats if c["name"] == "Coffee")
    payload = {k: coffee[k] for k in
               ("name", "icon", "tax_rate", "merchant_keywords",
                "rep_increment", "max_tax_rate", "daily_cap_amount")}
    payload["daily_cap_amount"] = 0.50
    rp = requests.patch(f"{API}/categories/{coffee['id']}", json=payload, headers=h)
    assert rp.status_code == 200 and rp.json()["daily_cap_amount"] == 0.50

    # Link, sync, process.
    requests.post(f"{API}/bank/link",
                  json={"provider": "spuerkeess", "access_token": "cap2-tok"}, headers=h)
    sync = requests.post(f"{API}/bank/sync", headers=h)
    assert sync.json()["ingested"] == 7
    proc = requests.post(f"{API}/tax/process", headers=h)
    assert proc.status_code == 200

    # Snapshot the two Coffee merchants and the default bucket.
    activity = requests.get(f"{API}/activity?limit=200", headers=h).json()
    sb = next(a for a in activity if "starbucks" in a["merchant_name"].lower())
    co = next(a for a in activity if "costa" in a["merchant_name"].lower())
    statuses = sorted([sb["status"], co["status"]])
    assert statuses == ["saved", "skipped"], \
        f"expected one saved + one skipped, got sb={sb['status']} co={co['status']}"

    # The saved one must have tax_amount > 0 and bucket should have increased by
    # exactly that amount worth of Coffee tax (not both Coffee taxes summed).
    saved_coffee = sb if sb["status"] == "saved" else co
    skipped_coffee = co if sb["status"] == "saved" else sb
    assert saved_coffee["tax_amount"] > 0
    assert skipped_coffee["tax_amount"] == 0
    # The cap is 0.50; tax shaved to cap if it would exceed.
    assert saved_coffee["tax_amount"] <= 0.50 + 1e-6, \
        f"saved coffee tax should be <= cap 0.50, got {saved_coffee['tax_amount']}"
