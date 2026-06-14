import os
import uuid
import logging
import random
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import List, Optional, Literal

import requests
from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr, Field

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
SECRET_KEY = os.getenv("JWT_SECRET", "eva-behavior-tax-dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30
OVERRIDE_WINDOW_MINUTES = 10

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

app = FastAPI(title="Eva — Behavior Tax")
api = APIRouter(prefix="/api")

# ---------- Models ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=60)
    currency: Literal["EUR", "USD", "GBP"] = "EUR"


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    currency: str
    default_bucket_id: Optional[str] = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class CategoryIn(BaseModel):
    name: str
    icon: str = "tag"
    tax_rate: float = Field(ge=0, le=1)
    merchant_keywords: List[str] = Field(default_factory=list)
    rep_increment: float = Field(default=0.05, ge=0, le=1)
    max_tax_rate: float = Field(default=0.50, ge=0, le=1)
    daily_cap_amount: float = Field(default=10.0, ge=0)


class CategoryOut(CategoryIn):
    id: str


class BucketIn(BaseModel):
    name: str
    target_amount: float = Field(ge=0)
    image_key: str = "travel"
    is_default: bool = False


class BucketOut(BaseModel):
    id: str
    name: str
    target_amount: float
    saved_amount: float
    image_key: str
    is_default: bool


class LinkedAccountIn(BaseModel):
    provider: Literal["revolut", "spuerkeess"]
    access_token: str = Field(min_length=4)


class LinkedAccountOut(BaseModel):
    id: str
    provider: str
    is_active: bool
    linked_at: datetime
    # Token never returned to client.


class ActivityRow(BaseModel):
    raw_txn_id: str
    merchant_name: str
    amount: float
    currency: str
    transacted_at: datetime
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    tax_event_id: Optional[str] = None
    tax_amount: float = 0.0
    tax_rate_applied: float = 0.0
    repetition_number: int = 0
    status: str  # "saved" | "skipped" | "overridden" | "unmatched"
    created_at: Optional[datetime] = None
    can_override: bool = False


# ---------- Helpers ----------
def hash_password(p: str) -> str:
    return pwd_context.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd_context.verify(p, h)


def create_token(uid: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": uid, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        uid = payload.get("sub")
    except JWTError:
        raise HTTPException(401, "Invalid token")
    user = await db.users.find_one({"id": uid}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return user


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


DEFAULT_CATEGORIES = [
    {"name": "Coffee", "icon": "coffee", "tax_rate": 0.25,
     "merchant_keywords": ["starbucks", "coffee", "café", "costa", "pret", "tim hortons"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 10.0},
    {"name": "Fast Food", "icon": "utensils", "tax_rate": 0.30,
     "merchant_keywords": ["mcdonalds", "burger king", "kfc", "subway", "five guys",
                           "uber eats", "deliveroo", "just eat"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 15.0},
    {"name": "Groceries", "icon": "shopping-cart", "tax_rate": 0.05,
     "merchant_keywords": ["carrefour", "aldi", "lidl", "delhaize", "colruyt",
                           "cactus", "match"],
     "rep_increment": 0.02, "max_tax_rate": 0.20, "daily_cap_amount": 20.0},
    {"name": "Clothes", "icon": "shopping-bag", "tax_rate": 0.15,
     "merchant_keywords": ["zara", "h&m", "primark", "uniqlo", "asos", "mango"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 25.0},
    {"name": "Entertainment", "icon": "film", "tax_rate": 0.20,
     "merchant_keywords": ["netflix", "spotify", "steam", "cinema", "ticketmaster"],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 15.0},
    {"name": "Transport", "icon": "car", "tax_rate": 0.10,
     "merchant_keywords": ["uber", "taxi", "stib", "tec", "de lijn", "parking"],
     "rep_increment": 0.03, "max_tax_rate": 0.30, "daily_cap_amount": 10.0},
    {"name": "Other", "icon": "tag", "tax_rate": 0.10,
     "merchant_keywords": [],  # catch-all, never auto-matches
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 10.0},
]


async def seed_user_defaults(user_id: str) -> str:
    for c in DEFAULT_CATEGORIES:
        await db.categories.insert_one({"id": str(uuid.uuid4()), "user_id": user_id, **c})
    bucket_id = str(uuid.uuid4())
    await db.buckets.insert_one({
        "id": bucket_id, "user_id": user_id,
        "name": "Travel Fund", "target_amount": 2000.0,
        "saved_amount": 0.0, "image_key": "travel", "is_default": True,
        "created_at": datetime.now(timezone.utc),
    })
    return bucket_id


# ---------- Auth ----------
@api.get("/")
async def root():
    return {"app": "Eva — Behavior Tax", "status": "ok"}


@api.post("/auth/register", response_model=Token, status_code=201)
async def register(data: UserCreate):
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())
    bucket_id = await seed_user_defaults(uid)
    user_doc = {
        "id": uid, "email": email, "name": data.name,
        "password_hash": hash_password(data.password),
        "currency": data.currency, "default_bucket_id": bucket_id,
        "created_at": datetime.now(timezone.utc),
    }
    await db.users.insert_one(user_doc)
    return Token(access_token=create_token(uid), user=to_user_out(user_doc))


@api.post("/auth/login", response_model=Token)
async def login(data: LoginBody):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    return Token(access_token=create_token(user["id"]), user=to_user_out(user))


@api.get("/auth/me", response_model=UserOut)
async def me(user=Depends(current_user)):
    return to_user_out(user)


@api.patch("/auth/me", response_model=UserOut)
async def update_me(
    currency: Optional[Literal["EUR", "USD", "GBP"]] = None,
    name: Optional[str] = None,
    default_bucket_id: Optional[str] = None,
    user=Depends(current_user),
):
    update = {}
    if currency is not None:
        update["currency"] = currency
    if name is not None:
        update["name"] = name
    if default_bucket_id is not None:
        b = await db.buckets.find_one({"id": default_bucket_id, "user_id": user["id"]})
        if not b:
            raise HTTPException(404, "Bucket not found")
        update["default_bucket_id"] = default_bucket_id
        # Also flip is_default flags for consistency.
        await db.buckets.update_many({"user_id": user["id"]}, {"$set": {"is_default": False}})
        await db.buckets.update_one({"id": default_bucket_id}, {"$set": {"is_default": True}})
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
        user.update(update)
    return to_user_out(user)


# ---------- Categories ----------
@api.get("/categories", response_model=List[CategoryOut])
async def list_categories(user=Depends(current_user)):
    rows = await db.categories.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    return [to_cat_out(r) for r in rows]


@api.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryIn, user=Depends(current_user)):
    cid = str(uuid.uuid4())
    await db.categories.insert_one({"id": cid, "user_id": user["id"], **data.model_dump()})
    return CategoryOut(id=cid, **data.model_dump())


@api.patch("/categories/{cid}", response_model=CategoryOut)
async def update_category(cid: str, data: CategoryIn, user=Depends(current_user)):
    res = await db.categories.update_one(
        {"id": cid, "user_id": user["id"]}, {"$set": data.model_dump()}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Category not found")
    return CategoryOut(id=cid, **data.model_dump())


@api.delete("/categories/{cid}")
async def delete_category(cid: str, user=Depends(current_user)):
    await db.categories.delete_one({"id": cid, "user_id": user["id"]})
    return {"ok": True}


# ---------- Buckets ----------
@api.get("/buckets", response_model=List[BucketOut])
async def list_buckets(user=Depends(current_user)):
    rows = await db.buckets.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    return [to_bucket_out(r) for r in rows]


@api.post("/buckets", response_model=BucketOut, status_code=201)
async def create_bucket(data: BucketIn, user=Depends(current_user)):
    bid = str(uuid.uuid4())
    doc = {
        "id": bid, "user_id": user["id"], "name": data.name,
        "target_amount": data.target_amount, "saved_amount": 0.0,
        "image_key": data.image_key, "is_default": data.is_default,
        "created_at": datetime.now(timezone.utc),
    }
    await db.buckets.insert_one(doc)
    if data.is_default:
        await db.buckets.update_many(
            {"user_id": user["id"], "id": {"$ne": bid}}, {"$set": {"is_default": False}}
        )
        await db.users.update_one({"id": user["id"]}, {"$set": {"default_bucket_id": bid}})
    return to_bucket_out(doc)


@api.patch("/buckets/{bid}", response_model=BucketOut)
async def update_bucket(bid: str, data: BucketIn, user=Depends(current_user)):
    res = await db.buckets.update_one(
        {"id": bid, "user_id": user["id"]},
        {"$set": {
            "name": data.name, "target_amount": data.target_amount,
            "image_key": data.image_key, "is_default": data.is_default,
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Bucket not found")
    if data.is_default:
        await db.buckets.update_many(
            {"user_id": user["id"], "id": {"$ne": bid}}, {"$set": {"is_default": False}}
        )
        await db.users.update_one({"id": user["id"]}, {"$set": {"default_bucket_id": bid}})
    b = await db.buckets.find_one({"id": bid, "user_id": user["id"]}, {"_id": 0})
    return to_bucket_out(b)


@api.delete("/buckets/{bid}")
async def delete_bucket(bid: str, user=Depends(current_user)):
    b = await db.buckets.find_one({"id": bid, "user_id": user["id"]})
    if not b:
        raise HTTPException(404, "Bucket not found")
    if b.get("is_default"):
        raise HTTPException(400, "Cannot delete the default bucket")
    await db.buckets.delete_one({"id": bid, "user_id": user["id"]})
    return {"ok": True}


# ---------- Bank linking ----------
@api.post("/bank/link", response_model=LinkedAccountOut, status_code=201)
async def link_bank(data: LinkedAccountIn, user=Depends(current_user)):
    # Deactivate any existing active account for this provider — one active token per provider per user.
    await db.linked_accounts.update_many(
        {"user_id": user["id"], "provider": data.provider, "is_active": True},
        {"$set": {"is_active": False}},
    )
    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "id": aid, "user_id": user["id"], "provider": data.provider,
        "access_token": data.access_token, "is_active": True, "linked_at": now,
    }
    await db.linked_accounts.insert_one(doc)
    return LinkedAccountOut(id=aid, provider=data.provider, is_active=True, linked_at=now)


@api.get("/bank/accounts", response_model=List[LinkedAccountOut])
async def list_accounts(user=Depends(current_user)):
    rows = await db.linked_accounts.find(
        {"user_id": user["id"], "is_active": True}, {"_id": 0, "access_token": 0}
    ).sort("linked_at", -1).to_list(20)
    return [
        LinkedAccountOut(
            id=r["id"], provider=r["provider"],
            is_active=r["is_active"], linked_at=ensure_aware(r["linked_at"]),
        )
        for r in rows
    ]


@api.delete("/bank/accounts/{aid}")
async def unlink_bank(aid: str, user=Depends(current_user)):
    res = await db.linked_accounts.update_one(
        {"id": aid, "user_id": user["id"]}, {"$set": {"is_active": False}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Linked account not found")
    return {"ok": True}


# ---------- Bank sync (ingestion) ----------
def _fetch_revolut(token: str) -> list:
    """Synchronous HTTP call run inside threadpool to keep the event loop free."""
    try:
        resp = requests.get(
            "https://sandbox-b2b.revolut.com/api/1.0/transactions",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Revolut sandbox unreachable: {e}")
    if resp.status_code == 401:
        raise HTTPException(401, "Revolut token rejected")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Revolut sandbox error {resp.status_code}")
    try:
        return resp.json() or []
    except ValueError:
        return []


def _parse_revolut(items: list) -> list:
    """Map Revolut sandbox payload to our raw_transactions shape. Best-effort parsing."""
    out = []
    for it in items:
        provider_id = it.get("id") or it.get("transaction_id")
        if not provider_id:
            continue
        merchant = (it.get("merchant") or {}).get("name") if isinstance(it.get("merchant"), dict) else None
        merchant = merchant or it.get("description") or it.get("reference") or "Unknown"
        # Amount: prefer leg.amount (negative for outflows). We invert to a positive "spent" value.
        legs = it.get("legs") or ([it.get("leg")] if it.get("leg") else [])
        amount = 0.0
        currency = "EUR"
        if legs:
            leg = legs[0] or {}
            amount = float(leg.get("amount") or 0.0)
            currency = leg.get("currency") or "EUR"
        else:
            amount = float(it.get("amount") or 0.0)
            currency = it.get("currency") or "EUR"
        if amount >= 0:  # ignore credits/inflows for now
            continue
        ts_raw = it.get("completed_at") or it.get("created_at")
        try:
            ts = datetime.fromisoformat((ts_raw or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)
        out.append({
            "provider_txn_id": str(provider_id),
            "merchant_name": str(merchant),
            "amount": abs(amount),
            "currency": currency,
            "transacted_at": ts,
        })
    return out


def _stub_spuerkeess() -> list:
    """Deterministic fake transactions for Spuerkeess (no real PSD2 sandbox)."""
    now = datetime.now(timezone.utc)
    # Each sync produces a fresh batch with provider_txn_id keyed on the day,
    # so dedup works inside a day but re-running on a new day pulls fresh tx.
    day_key = now.strftime("%Y%m%d%H%M%S")
    samples = [
        ("Starbucks Luxembourg-Ville", 4.80, 1),
        ("Cactus Belair", 38.20, 6),
        ("McDonalds Cloche d'Or", 9.50, 3),
        ("Uber Trip", 14.20, 2),
        ("Spotify AB", 9.99, 7),
        ("Zara Auchan", 64.90, 4),
        ("Costa Coffee Gare", 5.10, 1),
    ]
    return [
        {
            "provider_txn_id": f"spk_{i}_{day_key}",
            "merchant_name": m,
            "amount": amt,
            "currency": "EUR",
            "transacted_at": now - timedelta(days=days, minutes=(i * 47) % 600),
        }
        for i, (m, amt, days) in enumerate(samples)
    ]


@api.post("/bank/sync")
async def bank_sync(user=Depends(current_user)):
    accounts = await db.linked_accounts.find(
        {"user_id": user["id"], "is_active": True}, {"_id": 0}
    ).to_list(10)
    if not accounts:
        raise HTTPException(400, "No linked bank account")

    ingested = 0
    skipped_duplicates = 0
    for acc in accounts:
        provider = acc["provider"]
        if provider == "revolut":
            raw = await run_in_threadpool(_fetch_revolut, acc["access_token"])
            items = _parse_revolut(raw)
        else:  # spuerkeess stub
            items = _stub_spuerkeess()

        for it in items:
            existing = await db.raw_transactions.find_one({
                "user_id": user["id"],
                "account_id": acc["id"],
                "provider_txn_id": it["provider_txn_id"],
            })
            if existing:
                skipped_duplicates += 1
                continue
            await db.raw_transactions.insert_one({
                "id": str(uuid.uuid4()),
                "user_id": user["id"],
                "account_id": acc["id"],
                "provider_txn_id": it["provider_txn_id"],
                "merchant_name": it["merchant_name"],
                "amount": float(it["amount"]),
                "currency": it["currency"],
                "transacted_at": it["transacted_at"],
                "ingested_at": datetime.now(timezone.utc),
                "matched_category_id": None,
                "status": "pending",
            })
            ingested += 1

    return {"ingested": ingested, "duplicates": skipped_duplicates, "accounts": len(accounts)}


# ---------- Tax engine ----------
def _match_category(merchant: str, cats: list) -> Optional[dict]:
    name = (merchant or "").lower()
    for cat in cats:
        for kw in cat.get("merchant_keywords") or []:
            if kw and kw.lower() in name:
                return cat
    return None


@api.post("/tax/process")
async def tax_process(user=Depends(current_user)):
    pending = await db.raw_transactions.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    ).sort("transacted_at", 1).to_list(500)
    if not pending:
        return {"processed": 0, "taxed": 0, "skipped": 0, "unmatched": 0}

    cats = await db.categories.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    default_bucket_id = user.get("default_bucket_id")

    taxed = 0
    skipped = 0
    unmatched = 0

    for tx in pending:
        cat = _match_category(tx["merchant_name"], cats)
        if not cat:
            await db.raw_transactions.update_one(
                {"id": tx["id"]},
                {"$set": {"status": "unmatched", "matched_category_id": None}},
            )
            unmatched += 1
            continue

        today = ensure_aware(tx["transacted_at"]).date().isoformat()
        counter_key = {"user_id": user["id"], "category_id": cat["id"], "counter_date": today}
        counter = await db.daily_repetition_counters.find_one(counter_key)
        hit_count = counter["hit_count"] if counter else 0

        # Daily cap check across already-taxed events that occurred on the same
        # *transaction day*. (We key the cap on transacted_at, not created_at,
        # so back-dated rows from a fresh sync still respect the cap.)
        day_start = ensure_aware(tx["transacted_at"]).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        agg = await db.tax_events.aggregate([
            {"$match": {
                "user_id": user["id"], "category_id": cat["id"],
                "status": {"$in": ["pending", "transferred"]},
                "transacted_at": {"$gte": day_start, "$lt": day_end},
            }},
            {"$group": {"_id": None, "sum": {"$sum": "$tax_amount"}}},
        ]).to_list(1)
        taxed_today = float(agg[0]["sum"]) if agg else 0.0

        cap = float(cat.get("daily_cap_amount", 10.0))
        if taxed_today >= cap:
            await db.raw_transactions.update_one(
                {"id": tx["id"]},
                {"$set": {"status": "skipped", "matched_category_id": cat["id"]}},
            )
            skipped += 1
            continue

        base = float(cat["tax_rate"])
        inc = float(cat.get("rep_increment", 0.05))
        max_rate = float(cat.get("max_tax_rate", 0.50))
        effective_rate = min(max_rate, base + hit_count * inc)
        tax_amount = round(float(tx["amount"]) * effective_rate, 2)

        # Cap-aware tax: if applying full tax would exceed cap, shave to remaining.
        if taxed_today + tax_amount > cap:
            tax_amount = round(max(0.0, cap - taxed_today), 2)
        if tax_amount <= 0:
            await db.raw_transactions.update_one(
                {"id": tx["id"]},
                {"$set": {"status": "skipped", "matched_category_id": cat["id"]}},
            )
            skipped += 1
            continue

        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        await db.tax_events.insert_one({
            "id": event_id,
            "user_id": user["id"],
            "raw_txn_id": tx["id"],
            "category_id": cat["id"],
            "category_name": cat["name"],
            "bucket_id": default_bucket_id,
            "original_amount": float(tx["amount"]),
            "tax_rate_applied": effective_rate,
            "tax_amount": tax_amount,
            "repetition_number": hit_count + 1,
            "status": "pending",
            "override_reason": None,
            "transacted_at": ensure_aware(tx["transacted_at"]),
            "created_at": now,
        })
        # Increment daily counter.
        if counter:
            await db.daily_repetition_counters.update_one(
                {"id": counter["id"]}, {"$inc": {"hit_count": 1}}
            )
        else:
            await db.daily_repetition_counters.insert_one({
                "id": str(uuid.uuid4()), **counter_key, "hit_count": 1,
            })
        # Increment bucket (virtual transfer).
        if default_bucket_id:
            await db.buckets.update_one(
                {"id": default_bucket_id, "user_id": user["id"]},
                {"$inc": {"saved_amount": tax_amount}},
            )
        await db.raw_transactions.update_one(
            {"id": tx["id"]},
            {"$set": {"status": "taxed", "matched_category_id": cat["id"]}},
        )
        taxed += 1

    return {"processed": len(pending), "taxed": taxed, "skipped": skipped, "unmatched": unmatched}


@api.post("/tax/override/{event_id}")
async def tax_override(event_id: str, user=Depends(current_user)):
    ev = await db.tax_events.find_one({"id": event_id, "user_id": user["id"]})
    if not ev:
        raise HTTPException(404, "Tax event not found")
    if ev["status"] == "overridden":
        raise HTTPException(400, "Already overridden")
    created = ensure_aware(ev["created_at"])
    age = datetime.now(timezone.utc) - created
    if age > timedelta(minutes=OVERRIDE_WINDOW_MINUTES):
        raise HTTPException(400, "Override window has passed")
    await db.tax_events.update_one(
        {"id": event_id},
        {"$set": {"status": "overridden", "override_reason": "intentional"}},
    )
    # Roll back bucket increment.
    if ev.get("bucket_id"):
        await db.buckets.update_one(
            {"id": ev["bucket_id"], "user_id": user["id"]},
            {"$inc": {"saved_amount": -float(ev["tax_amount"])}},
        )
    return {"ok": True}


@api.post("/tax/transfer")
async def tax_transfer(user=Depends(current_user)):
    pending = await db.tax_events.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    ).to_list(1000)
    if not pending:
        return {"transferred": 0, "total_amount": 0.0}
    total = round(sum(float(e["tax_amount"]) for e in pending), 2)
    ids = [e["id"] for e in pending]
    transfer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.tax_transfers.insert_one({
        "id": transfer_id, "user_id": user["id"], "total_amount": total,
        "tax_event_ids": ids, "status": "simulated", "executed_at": now,
    })
    await db.tax_events.update_many(
        {"user_id": user["id"], "id": {"$in": ids}}, {"$set": {"status": "transferred"}}
    )
    return {"transferred": len(ids), "total_amount": total, "transfer_id": transfer_id}


# ---------- Activity feed ----------
@api.get("/activity", response_model=List[ActivityRow])
async def activity_feed(limit: int = 100, user=Depends(current_user)):
    rows = await db.raw_transactions.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("transacted_at", -1).to_list(limit)
    if not rows:
        return []
    # Pull matched tax_events (if any) for these raw_tx ids.
    raw_ids = [r["id"] for r in rows]
    events = await db.tax_events.find(
        {"user_id": user["id"], "raw_txn_id": {"$in": raw_ids}}, {"_id": 0}
    ).to_list(len(raw_ids) * 2)
    ev_by_raw = {e["raw_txn_id"]: e for e in events}

    now = datetime.now(timezone.utc)
    out: List[ActivityRow] = []
    for r in rows:
        ev = ev_by_raw.get(r["id"])
        if ev:
            created = ensure_aware(ev["created_at"])
            can_override = (
                ev["status"] in ("pending", "transferred")
                and (now - created) <= timedelta(minutes=OVERRIDE_WINDOW_MINUTES)
            )
            status_label = {
                "pending": "saved",
                "transferred": "saved",
                "overridden": "overridden",
            }.get(ev["status"], "saved")
            out.append(ActivityRow(
                raw_txn_id=r["id"],
                merchant_name=r["merchant_name"],
                amount=float(r["amount"]),
                currency=r.get("currency", "EUR"),
                transacted_at=ensure_aware(r["transacted_at"]),
                category_id=ev.get("category_id"),
                category_name=ev.get("category_name"),
                tax_event_id=ev["id"],
                tax_amount=float(ev["tax_amount"]),
                tax_rate_applied=float(ev["tax_rate_applied"]),
                repetition_number=int(ev.get("repetition_number", 1)),
                status=status_label,
                created_at=created,
                can_override=can_override,
            ))
        else:
            # No tax event: either skipped (cap) or unmatched (no keyword)
            label = "skipped" if r["status"] == "skipped" else (
                "unmatched" if r["status"] == "unmatched" else "pending"
            )
            out.append(ActivityRow(
                raw_txn_id=r["id"],
                merchant_name=r["merchant_name"],
                amount=float(r["amount"]),
                currency=r.get("currency", "EUR"),
                transacted_at=ensure_aware(r["transacted_at"]),
                category_id=r.get("matched_category_id"),
                category_name=None,
                tax_event_id=None,
                tax_amount=0.0,
                tax_rate_applied=0.0,
                repetition_number=0,
                status=label,
                created_at=None,
                can_override=False,
            ))
    return out


# ---------- Insights ----------
@api.get("/insights/summary")
async def insights_summary(user=Depends(current_user)):
    # Aggregate from tax_events (real engine output), not raw transactions.
    base_match = {"user_id": user["id"], "status": {"$in": ["pending", "transferred"]}}
    agg = await db.tax_events.aggregate([
        {"$match": base_match},
        {"$group": {
            "_id": None,
            "total_taxed": {"$sum": "$tax_amount"},
            "total_spent": {"$sum": "$original_amount"},
            "count": {"$sum": 1},
        }},
    ]).to_list(1)
    totals = agg[0] if agg else {"total_spent": 0, "total_taxed": 0, "count": 0}

    by_cat = await db.tax_events.aggregate([
        {"$match": base_match},
        {"$group": {
            "_id": "$category_name",
            "spent": {"$sum": "$original_amount"},
            "taxed": {"$sum": "$tax_amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"spent": -1}},
    ]).to_list(100)

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    by_day = await db.tax_events.aggregate([
        {"$match": {**base_match, "created_at": {"$gte": week_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "spent": {"$sum": "$original_amount"},
            "taxed": {"$sum": "$tax_amount"},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(31)

    # Streak: days since last *taxed* event.
    last = await db.tax_events.find_one(
        {"user_id": user["id"], "status": {"$in": ["pending", "transferred"]}},
        sort=[("created_at", -1)],
    )
    days_since = 0
    if last:
        days_since = max(0, (datetime.now(timezone.utc) - ensure_aware(last["created_at"])).days)

    return {
        "total_spent": round(totals.get("total_spent", 0), 2),
        "total_taxed": round(totals.get("total_taxed", 0), 2),
        "transactions": totals.get("count", 0),
        "by_category": [
            {"name": r["_id"], "spent": round(r["spent"], 2),
             "taxed": round(r["taxed"], 2), "count": r["count"]}
            for r in by_cat
        ],
        "by_day": [
            {"date": r["_id"], "spent": round(r["spent"], 2), "taxed": round(r["taxed"], 2)}
            for r in by_day
        ],
        "streak_days_no_impulse": days_since,
    }


# ---------- Wiring ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
