import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Literal
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
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

# Revolut Open Banking personal sandbox.
REVOLUT_CLIENT_ID = os.getenv("REVOLUT_CLIENT_ID", "05f4b015-b95a-423b-a7c8-c4e33c17b97d")
REVOLUT_AUTH_URL = "https://sandbox-oba.revolut.com/ui/index.html"
REVOLUT_TOKEN_URL = "https://sandbox-oba.revolut.com/token"
REVOLUT_API_BASE = "https://sandbox-oba.revolut.com"
REVOLUT_REDIRECT_FALLBACK = os.getenv("REVOLUT_REDIRECT_URI", "")  # optional override

# Behavioral profiles.
PROFILES = ("balanced", "aggressive", "ethical", "mindful", "savings_beast")
ETHICAL_PENALTY_CATS = {"Fast Food", "Clothes", "Entertainment", "Ethical Penalty"}
SAVINGS_BEAST_TRIGGER_AMOUNT = 5.00

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
    # Optional: legacy/direct-token mode (Spuerkeess always; Revolut tests).
    # When omitted for Revolut, we initiate the OAuth consent flow instead.
    access_token: Optional[str] = None


class LinkedAccountOut(BaseModel):
    id: str
    provider: str
    is_active: bool
    linked_at: datetime
    # Present only for fresh Revolut OAuth links — frontend opens this URL in a WebView.
    consent_url: Optional[str] = None


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
    status: str
    created_at: Optional[datetime] = None
    can_override: bool = False
    profile_applied: Optional[str] = None


class SettingsIn(BaseModel):
    profile_type: Optional[Literal["balanced", "aggressive", "ethical", "mindful", "savings_beast"]] = None
    transfer_frequency: Optional[Literal["instant", "daily", "weekly"]] = None
    pause_all_taxes: Optional[bool] = None


class SettingsOut(BaseModel):
    profile_type: str
    transfer_frequency: str
    pause_all_taxes: bool


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


def to_settings_out(u: dict) -> SettingsOut:
    return SettingsOut(
        profile_type=u.get("profile_type", "balanced"),
        transfer_frequency=u.get("transfer_frequency", "instant"),
        pause_all_taxes=bool(u.get("pause_all_taxes", False)),
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
     "merchant_keywords": [],
     "rep_increment": 0.05, "max_tax_rate": 0.50, "daily_cap_amount": 10.0},
    # Ethical-profile target category; matched only when ethical-profile keywords appear in merchant.
    {"name": "Ethical Penalty", "icon": "alert-triangle", "tax_rate": 0.35,
     "merchant_keywords": ["amazon", "mcdonalds", "kfc", "primark", "h&m",
                           "coca-cola", "pepsi", "nestlé", "monsanto", "shein"],
     "rep_increment": 0.05, "max_tax_rate": 0.70, "daily_cap_amount": 20.0},
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


def apply_profile_multiplier(rate: float, cat_name: str, profile: str, max_rate: float) -> float:
    """Apply the behavioral profile multiplier on top of the (already rep-adjusted) rate."""
    if profile == "aggressive" or profile == "savings_beast":
        rate = rate * 1.5
    elif profile == "ethical":
        if cat_name in ETHICAL_PENALTY_CATS:
            rate = rate * 1.4
    elif profile == "mindful":
        rate = rate * 0.5
    # balanced -> no change
    return min(max_rate, rate)


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
        "profile_type": "balanced",
        "transfer_frequency": "instant",
        "pause_all_taxes": False,
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
        await db.buckets.update_many({"user_id": user["id"]}, {"$set": {"is_default": False}})
        await db.buckets.update_one({"id": default_bucket_id}, {"$set": {"is_default": True}})
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
        user.update(update)
    return to_user_out(user)


# ---------- Settings ----------
@api.get("/settings", response_model=SettingsOut)
async def get_settings(user=Depends(current_user)):
    return to_settings_out(user)


@api.patch("/settings", response_model=SettingsOut)
async def patch_settings(data: SettingsIn, user=Depends(current_user)):
    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
        user.update(update)
    return to_settings_out(user)


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
def _revolut_callback_url(request: Request) -> str:
    if REVOLUT_REDIRECT_FALLBACK:
        return REVOLUT_REDIRECT_FALLBACK
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/bank/revolut/callback"


def _revolut_consent_url(state: str, redirect_uri: str) -> str:
    params = {
        "client_id": REVOLUT_CLIENT_ID,
        "response_type": "code",
        "scope": "accounts",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{REVOLUT_AUTH_URL}?{urlencode(params)}"


@api.post("/bank/link", response_model=LinkedAccountOut, status_code=201)
async def link_bank(data: LinkedAccountIn, request: Request, user=Depends(current_user)):
    # One active record per provider per user — deactivate any prior.
    await db.linked_accounts.update_many(
        {"user_id": user["id"], "provider": data.provider, "is_active": True},
        {"$set": {"is_active": False}},
    )

    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Revolut + no access_token => OAuth consent flow.
    if data.provider == "revolut" and not data.access_token:
        state = uuid.uuid4().hex
        redirect_uri = _revolut_callback_url(request)
        doc = {
            "id": aid, "user_id": user["id"], "provider": "revolut",
            "access_token": "", "refresh_token": None, "token_expires_at": None,
            "is_active": False,  # becomes active after callback succeeds
            "oauth_state": state, "redirect_uri": redirect_uri,
            "linked_at": now,
        }
        await db.linked_accounts.insert_one(doc)
        return LinkedAccountOut(
            id=aid, provider="revolut", is_active=False, linked_at=now,
            consent_url=_revolut_consent_url(state, redirect_uri),
        )

    # Legacy / direct-token path (Spuerkeess always; Revolut when token explicitly supplied for tests).
    doc = {
        "id": aid, "user_id": user["id"], "provider": data.provider,
        "access_token": data.access_token or "stub",
        "refresh_token": None, "token_expires_at": None,
        "is_active": True, "oauth_state": None,
        "linked_at": now,
    }
    await db.linked_accounts.insert_one(doc)
    return LinkedAccountOut(
        id=aid, provider=data.provider, is_active=True, linked_at=now, consent_url=None,
    )


@api.get("/bank/accounts", response_model=List[LinkedAccountOut])
async def list_accounts(user=Depends(current_user)):
    rows = await db.linked_accounts.find(
        {"user_id": user["id"], "is_active": True},
        {"_id": 0, "access_token": 0, "refresh_token": 0, "oauth_state": 0},
    ).sort("linked_at", -1).to_list(20)
    return [
        LinkedAccountOut(
            id=r["id"], provider=r["provider"],
            is_active=r["is_active"], linked_at=ensure_aware(r["linked_at"]),
            consent_url=None,
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


# Revolut OAuth callback. Browser/WebView lands here after Revolut auth.
@api.get("/bank/revolut/callback", name="revolut_callback")
async def revolut_callback(code: Optional[str] = None, state: Optional[str] = None,
                           error: Optional[str] = None):
    if error:
        return HTMLResponse(_callback_page(f"Revolut returned: {error}"), status_code=400)
    if not code or not state:
        return HTMLResponse(_callback_page("Missing code or state."), status_code=400)
    acc = await db.linked_accounts.find_one({"oauth_state": state})
    if not acc:
        return HTMLResponse(_callback_page("State not recognised."), status_code=404)

    redirect_uri = acc.get("redirect_uri")
    try:
        token_data = await run_in_threadpool(_revolut_exchange_code, code, redirect_uri)
    except HTTPException as e:
        return HTMLResponse(_callback_page(f"Token exchange failed: {e.detail}"), status_code=502)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in") or 3600))
    await db.linked_accounts.update_one(
        {"id": acc["id"]},
        {"$set": {
            "access_token": token_data.get("access_token") or "",
            "refresh_token": token_data.get("refresh_token"),
            "token_expires_at": expires_at,
            "is_active": True,
            "oauth_state": None,
        }},
    )
    return HTMLResponse(_callback_page("All set — you can close this window and return to Éva.", success=True))


def _callback_page(msg: str, success: bool = False) -> str:
    color = "#7B8C73" if success else "#C27D72"
    # The deep-link href lets a mobile WebBrowser session auto-close.
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Éva — Revolut</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;background:#F7F5F2;color:#282624;padding:48px 24px;text-align:center}}
h1{{color:{color};font-size:22px;margin:0 0 12px}}p{{color:#3E3B37}}a{{color:#7B8C73;text-decoration:none;font-weight:600}}</style>
</head><body>
<h1>{"Bank linked" if success else "Couldn't link"}</h1>
<p>{msg}</p>
<p><a href="eva://bank-callback?status={'ok' if success else 'error'}">Return to Éva</a></p>
<script>setTimeout(function(){{window.location='eva://bank-callback?status={'ok' if success else 'error'}'}}, 800);</script>
</body></html>"""


def _revolut_exchange_code(code: str, redirect_uri: Optional[str]) -> dict:
    try:
        resp = requests.post(
            REVOLUT_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri or "",
                "client_id": REVOLUT_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Token endpoint unreachable: {e}")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Token endpoint error {resp.status_code}: {resp.text[:160]}")
    try:
        return resp.json()
    except ValueError:
        raise HTTPException(502, "Token endpoint returned non-JSON")


def _revolut_refresh(refresh_token: str) -> dict:
    try:
        resp = requests.post(
            REVOLUT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": REVOLUT_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Refresh endpoint unreachable: {e}")
    if resp.status_code == 401:
        raise HTTPException(401, "Refresh token rejected")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Refresh error {resp.status_code}")
    return resp.json()


# ---------- Bank sync (ingestion) ----------
def _fetch_revolut_personal(token: str) -> list:
    """Call the personal Open Banking sandbox transactions endpoint."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        # Standard PSD2 AISP path. Server returns 401 for invalid tokens — matches existing tests.
        resp = requests.get(f"{REVOLUT_API_BASE}/transactions", headers=headers, timeout=15)
    except requests.RequestException as e:
        raise HTTPException(502, f"Revolut unreachable: {e}")
    if resp.status_code == 401:
        raise HTTPException(401, "Revolut token rejected")
    if resp.status_code == 404:
        # Fallback to /accounts → /accounts/{id}/transactions in newer sandbox builds.
        try:
            accs = requests.get(f"{REVOLUT_API_BASE}/accounts", headers=headers, timeout=15)
        except requests.RequestException as e:
            raise HTTPException(502, f"Revolut accounts unreachable: {e}")
        if accs.status_code == 401:
            raise HTTPException(401, "Revolut token rejected")
        if accs.status_code >= 400:
            raise HTTPException(502, f"Revolut accounts error {accs.status_code}")
        try:
            data = accs.json()
        except ValueError:
            return []
        ids = []
        # Open Banking standard shape: {"Data": {"Account": [{"AccountId": "..."}]}}
        for a in (data.get("Data", {}).get("Account") or []):
            aid = a.get("AccountId") or a.get("id")
            if aid:
                ids.append(aid)
        agg = []
        for aid in ids:
            try:
                tr = requests.get(f"{REVOLUT_API_BASE}/accounts/{aid}/transactions", headers=headers, timeout=15)
            except requests.RequestException:
                continue
            if tr.status_code < 400:
                try:
                    tj = tr.json()
                    agg.extend(tj.get("Data", {}).get("Transaction") or tj or [])
                except ValueError:
                    pass
        return agg
    if resp.status_code >= 400:
        raise HTTPException(502, f"Revolut error {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        return []
    # Either a flat array or an Open Banking-style wrapper.
    if isinstance(body, list):
        return body
    return body.get("Data", {}).get("Transaction") or body.get("transactions") or []


def _parse_revolut(items: list) -> list:
    """Map Revolut payload to our raw_transactions shape. Best-effort across personal and B2B shapes."""
    out = []
    for it in items:
        provider_id = it.get("TransactionId") or it.get("id") or it.get("transaction_id")
        if not provider_id:
            continue
        # merchant name across shapes
        merch = it.get("MerchantDetails", {}).get("MerchantName") if isinstance(it.get("MerchantDetails"), dict) else None
        if not merch and isinstance(it.get("merchant"), dict):
            merch = it["merchant"].get("name")
        merch = merch or it.get("TransactionInformation") or it.get("description") or it.get("reference") or "Unknown"
        # amount across shapes
        amount = 0.0
        currency = "EUR"
        amt_obj = it.get("Amount")
        if isinstance(amt_obj, dict):
            amount = float(amt_obj.get("Amount") or 0.0)
            currency = amt_obj.get("Currency") or "EUR"
            # CreditDebitIndicator: "Credit" inflow, "Debit" outflow. Convention: treat Debit as negative.
            if (it.get("CreditDebitIndicator") or "").lower() == "debit":
                amount = -abs(amount)
            elif (it.get("CreditDebitIndicator") or "").lower() == "credit":
                amount = abs(amount)
        else:
            legs = it.get("legs") or ([it.get("leg")] if it.get("leg") else [])
            if legs:
                leg = legs[0] or {}
                amount = float(leg.get("amount") or 0.0)
                currency = leg.get("currency") or "EUR"
            else:
                amount = float(it.get("amount") or 0.0)
                currency = it.get("currency") or "EUR"
        if amount >= 0:  # inflow / credit — skip
            continue
        ts_raw = (
            it.get("BookingDateTime") or it.get("ValueDateTime")
            or it.get("completed_at") or it.get("created_at")
        )
        try:
            ts = datetime.fromisoformat((ts_raw or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)
        out.append({
            "provider_txn_id": str(provider_id),
            "merchant_name": str(merch),
            "amount": abs(amount),
            "currency": currency,
            "transacted_at": ts,
        })
    return out


def _stub_spuerkeess() -> list:
    now = datetime.now(timezone.utc)
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


async def _refresh_revolut_if_needed(acc: dict) -> str:
    """Returns a fresh access_token, refreshing it via the OAuth refresh flow if expired."""
    token = acc.get("access_token") or ""
    expires_at = acc.get("token_expires_at")
    if not expires_at or not acc.get("refresh_token"):
        return token  # legacy direct-token mode; let the call surface the error.
    expires_at = ensure_aware(expires_at)
    if datetime.now(timezone.utc) < expires_at - timedelta(seconds=60):
        return token
    fresh = await run_in_threadpool(_revolut_refresh, acc["refresh_token"])
    new_access = fresh.get("access_token") or ""
    new_refresh = fresh.get("refresh_token") or acc["refresh_token"]
    new_exp = datetime.now(timezone.utc) + timedelta(seconds=int(fresh.get("expires_in") or 3600))
    await db.linked_accounts.update_one(
        {"id": acc["id"]},
        {"$set": {
            "access_token": new_access, "refresh_token": new_refresh, "token_expires_at": new_exp,
        }},
    )
    return new_access


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
            token = await _refresh_revolut_if_needed(acc)
            raw = await run_in_threadpool(_fetch_revolut_personal, token)
            items = _parse_revolut(raw)
        else:
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
    # Iterate in DB-insertion order; "Ethical Penalty" is last so it only matches when
    # its specific brands are present *and* nothing else matched first. But because
    # we want it to take precedence for explicit brand hits (e.g. Primark, Amazon),
    # check it FIRST.
    ordered = sorted(cats, key=lambda c: 0 if c.get("name") == "Ethical Penalty" else 1)
    for cat in ordered:
        for kw in cat.get("merchant_keywords") or []:
            if kw and kw.lower() in name:
                return cat
    return None


async def _maybe_auto_transfer(user: dict):
    """Savings-Beast: if pending taxes exceed the trigger amount, transfer them inline."""
    if user.get("profile_type") != "savings_beast":
        return None
    pending = await db.tax_events.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    ).to_list(1000)
    total = round(sum(float(e["tax_amount"]) for e in pending), 2)
    if total <= SAVINGS_BEAST_TRIGGER_AMOUNT or not pending:
        return None
    ids = [e["id"] for e in pending]
    transfer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.tax_transfers.insert_one({
        "id": transfer_id, "user_id": user["id"], "total_amount": total,
        "tax_event_ids": ids, "status": "simulated", "executed_at": now,
        "trigger": "savings_beast_auto",
    })
    await db.tax_events.update_many(
        {"user_id": user["id"], "id": {"$in": ids}}, {"$set": {"status": "transferred"}}
    )
    return {"transferred": len(ids), "total_amount": total, "transfer_id": transfer_id}


@api.post("/tax/process")
async def tax_process(user=Depends(current_user)):
    if user.get("pause_all_taxes"):
        return {"paused": True}

    pending = await db.raw_transactions.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    ).sort("transacted_at", 1).to_list(500)
    if not pending:
        return {"processed": 0, "taxed": 0, "skipped": 0, "unmatched": 0}

    cats = await db.categories.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    default_bucket_id = user.get("default_bucket_id")
    profile = user.get("profile_type", "balanced")

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

        today_iso = ensure_aware(tx["transacted_at"]).date().isoformat()
        counter_key = {"user_id": user["id"], "category_id": cat["id"], "counter_date": today_iso}
        counter = await db.daily_repetition_counters.find_one(counter_key)
        hit_count = counter["hit_count"] if counter else 0

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
        rep_rate = min(max_rate, base + hit_count * inc)
        # Apply behavioral profile multiplier on top of the rep-adjusted rate.
        effective_rate = apply_profile_multiplier(rep_rate, cat["name"], profile, max_rate)
        tax_amount = round(float(tx["amount"]) * effective_rate, 2)

        # Cap-aware tax: shave to remaining cap.
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
            "profile_applied": profile,
            "transacted_at": ensure_aware(tx["transacted_at"]),
            "created_at": now,
        })
        if counter:
            await db.daily_repetition_counters.update_one(
                {"id": counter["id"]}, {"$inc": {"hit_count": 1}}
            )
        else:
            await db.daily_repetition_counters.insert_one({
                "id": str(uuid.uuid4()), **counter_key, "hit_count": 1,
            })
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

    result = {"processed": len(pending), "taxed": taxed, "skipped": skipped, "unmatched": unmatched}

    auto = await _maybe_auto_transfer(user)
    if auto:
        result["auto_transfer"] = auto
    return result


@api.post("/tax/override/{event_id}")
async def tax_override(event_id: str, user=Depends(current_user)):
    ev = await db.tax_events.find_one({"id": event_id, "user_id": user["id"]})
    if not ev:
        raise HTTPException(404, "Tax event not found")
    if ev["status"] == "overridden":
        raise HTTPException(400, "Already overridden")
    created = ensure_aware(ev["created_at"])
    if datetime.now(timezone.utc) - created > timedelta(minutes=OVERRIDE_WINDOW_MINUTES):
        raise HTTPException(400, "Override window has passed")
    await db.tax_events.update_one(
        {"id": event_id},
        {"$set": {"status": "overridden", "override_reason": "intentional"}},
    )
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
        "trigger": "manual",
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
                "pending": "saved", "transferred": "saved", "overridden": "overridden",
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
                profile_applied=ev.get("profile_applied", "balanced"),
            ))
        else:
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
                profile_applied=None,
            ))
    return out


# ---------- Insights ----------
@api.get("/insights/summary")
async def insights_summary(user=Depends(current_user)):
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
        "profile_type": user.get("profile_type", "balanced"),
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
