from datetime import datetime, timedelta, timezone

from utils import ensure_aware


def stub_spuerkeess(connected_at: datetime, fixed_time: datetime = None) -> list:
    """Generate transactions after connection time so sync never taxes old purchases."""
    now = fixed_time if fixed_time else datetime.now(timezone.utc)
    day_key = now.strftime("%Y%m%d%H%M%S")

    samples = [
        ("Starbucks Luxembourg-Ville", 4.80, 5, "spk_main", "Spuerkeess · Checking", "account"),
        ("Cactus Belair", 38.20, 90, "spk_main", "Spuerkeess · Checking", "account"),
        ("McDonalds Cloche d'Or", 9.50, 120, "spk_main", "Spuerkeess · Checking", "account"),
        ("Uber Trip", 14.20, 180, "spk_card_1234", "Spuerkeess · Card *1234", "card"),
        ("Spotify AB", 9.99, 240, "spk_main", "Spuerkeess · Checking", "account"),
        ("Zara Auchan", 64.90, 300, "spk_card_1234", "Spuerkeess · Card *1234", "card"),
        ("Costa Coffee Gare", 5.10, 30, "spk_main", "Spuerkeess · Checking", "account"),
    ]
    out = []
    for i, (m, amt, mins, sid, slabel, stype) in enumerate(samples):
        out.append({
            "provider_txn_id": f"spk_{i}_{day_key}",
            "merchant_name": m,
            "amount": amt,
            "currency": "EUR",
            "transacted_at": ensure_aware(connected_at) + timedelta(minutes=mins),
            "source_account_id": sid,
            "source_label": slabel,
            "source_type": stype,
            "source_currency": "EUR",
        })
    return out
