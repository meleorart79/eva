from schemas import (
    BucketOut,
    CategoryOut,
    SavingsDestinationOut,
    SettingsOut,
    UserOut,
)
from utils import ensure_aware


def to_user_out(u: dict) -> UserOut:
    return UserOut(
        id=u["id"], email=u["email"], name=u["name"],
        currency=u["currency"], default_bucket_id=u.get("default_bucket_id"),
    )


def to_cat_out(r: dict) -> CategoryOut:
    return CategoryOut(
        id=r["id"], name=r["name"], icon=r.get("icon", "tag"),
        tax_rate=r["tax_rate"],
        merchant_keywords=r.get("merchant_keywords", []),
        rep_increment=r.get("rep_increment", 0.05),
        max_tax_rate=r.get("max_tax_rate", 0.50),
        daily_cap_amount=r.get("daily_cap_amount", 10.0),
    )


def to_bucket_out(b: dict) -> BucketOut:
    return BucketOut(
        id=b["id"], name=b["name"], target_amount=b["target_amount"],
        saved_amount=b.get("saved_amount", 0.0), image_key=b.get("image_key", "travel"),
        is_default=b.get("is_default", False),
    )


def to_dest_out(d: dict) -> SavingsDestinationOut:
    return SavingsDestinationOut(
        id=d["id"], type=d["type"], label=d["label"],
        identifier=d["identifier"], currency=d["currency"],
        is_default=bool(d.get("is_default", False)),
        is_active=bool(d.get("is_active", True)),
        created_at=ensure_aware(d["created_at"]),
    )


def to_settings_out(u: dict) -> SettingsOut:
    last = u.get("transfer_last_run_at")
    return SettingsOut(
        profile_type=u.get("profile_type", "balanced"),
        transfer_frequency=u.get("transfer_frequency", "instant"),
        pause_all_taxes=bool(u.get("pause_all_taxes", False)),
        apply_ethical_penalty_all_profiles=u.get("apply_ethical_penalty_all_profiles", False),
        transfer_last_run_at=ensure_aware(last) if last else None,
    )
