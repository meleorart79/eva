import os
import io
import csv
import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Literal
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
from jose import jwt, JWTError
from contextlib import asynccontextmanager

from constants import (
    DEFAULT_CATEGORIES,
    DEST_TYPES,
    ETHICAL_PENALTY_CATS,
    EXPO_PUSH_URL,
    FREQUENCIES,
    PROFILES,
    REVOLUT_API_BASE,
    REVOLUT_AUTH_URL,
    REVOLUT_CLIENT_ID,
    REVOLUT_REDIRECT_FALLBACK,
    REVOLUT_TOKEN_URL,
    SAVINGS_BEAST_TRIGGER_AMOUNT,
    TRANSFER_STATUSES,
)
from mappers import (
    to_bucket_out,
    to_cat_out,
    to_dest_out,
    to_settings_out,
    to_user_out,
)
from providers.spuerkeess import stub_spuerkeess as _stub_spuerkeess
from schemas import (
    ActivityRow,
    BucketIn,
    BucketOut,
    CategoryIn,
    CategoryOut,
    LinkedAccountIn,
    LinkedAccountOut,
    LoginBody,
    PushTokenIn,
    ResolveReviewIn,
    SavingsDestinationIn,
    SavingsDestinationOut,
    SettingsIn,
    SettingsOut,
    Token,
    UserCreate,
    UserOut,
)
from utils import ensure_aware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
SECRET_KEY = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30
OVERRIDE_WINDOW_MINUTES = 10

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    try:
        await client.admin.command("ping")
    except Exception as e:
        raise RuntimeError(f"MongoDB startup check failed: {e}")

    async def scheduler_loop():
        while True:
            try:
                await asyncio.sleep(60)
                await _run_scheduler_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Scheduler loop iteration failed")

    task = asyncio.create_task(scheduler_loop())

    yield  # app runs here

    # --- shutdown ---
    task.cancel()
    client.close()

app = FastAPI(title="Eva — Behavior Tax", lifespan=lifespan)
api = APIRouter(prefix="/api")

# ---------- Helpers ----------
def hash_password(p: str) -> str:
    return pwd_context.hash(p)


def verify_password(p: str, h: str) -> bool:
    return pwd_context.verify(p, h)


def create_token(uid: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": uid, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


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

def send_push(token: str, title: str, body: str):
    requests.post(EXPO_PUSH_URL, json={
        "to": token,
        "title": title,
        "body": body,
    })

async def seed_user_defaults(user_id: str, currency: str) -> str:
    now = datetime.now(timezone.utc)
    for c in DEFAULT_CATEGORIES:
        await db.categories.insert_one({"id": str(uuid.uuid4()), "user_id": user_id, **c})
    bucket_id = str(uuid.uuid4())
    await db.buckets.insert_one({
        "id": bucket_id, "user_id": user_id,
        "name": "Travel Fund", "target_amount": 2000.0,
        "saved_amount": 0.0, "image_key": "travel", "is_default": True,
        "created_at": now,
    })
    # Seed a default Revolut-style savings pocket so the transfer loop works
    # out of the box. User can replace with their own destination from Settings.
    await db.savings_destinations.insert_one({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "type": "revolut_pocket",
        "label": "Default Savings Pocket",
        "identifier": f"pocket_{user_id[:8]}",
        "currency": currency,
        "is_default": True, "is_active": True,
        "created_at": now,
    })
    return bucket_id


def apply_profile_multiplier(rate, cat_name, profile, max_rate, apply_ethical_all):
    if profile == "aggressive" or profile == "savings_beast":
        rate = rate * 1.5
    elif profile == "mindful":
        rate = rate * 0.5

    ethical_penalty_applies = cat_name in ETHICAL_PENALTY_CATS and (
        apply_ethical_all or profile == "ethical"
    )
    if ethical_penalty_applies:
        rate = rate * 1.4

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
    bucket_id = await seed_user_defaults(uid, data.currency)
    user_doc = {
        "id": uid, "email": email, "name": data.name,
        "password_hash": hash_password(data.password),
        "currency": data.currency, "default_bucket_id": bucket_id,
        "profile_type": "balanced",
        "transfer_frequency": "instant",
        "pause_all_taxes": False,
        "transfer_last_run_at": None,
        "created_at": datetime.now(timezone.utc),
        "apply_ethical_penalty_all_profiles": False,
        "expo_push_token": None,
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

@api.post("/tax/events/{event_id}/resolve-review")
async def resolve_review(event_id: str, data: ResolveReviewIn, user=Depends(current_user)):
    ev = await db.tax_events.find_one({"id": event_id, "user_id": user["id"]})
    if not ev:
        raise HTTPException(404, "Tax event not found")
    if not ev.get("requires_review"):
        raise HTTPException(400, "Event does not require review")

    if data.action == "approve":
        await db.tax_events.update_one(
            {"id": event_id},
            {"$set": {"requires_review": False, "review_reason": None, "transfer_status": "pending"}},
        )
        return {"ok": True}

    if not data.destination_id:
        raise HTTPException(400, "destination_id required")
    dest = await db.savings_destinations.find_one(
        {"id": data.destination_id, "user_id": user["id"], "is_active": True}
    )
    if not dest:
        raise HTTPException(404, "Destination not found")
    await db.tax_events.update_one(
        {"id": event_id},
        {"$set": {
            "destination_id": dest["id"],
            "destination_label": dest["label"],
            "destination_currency": dest["currency"],
            "requires_review": False,
            "review_reason": None,
            "transfer_status": "pending",
        }},
    )
    return {"ok": True}

@api.post("/notifications/register")
async def register_push_token(
    data: PushTokenIn,
    user=Depends(current_user),
):
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"expo_push_token": data.token}},
    )

    return {"ok": True}

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


# ---------- Savings destinations ----------
async def _validate_destination_currency(user: dict, currency: str):
    """Destination currency must match user currency OR a linked-account currency."""
    if currency == user.get("currency"):
        return
    # Look at any active linked account's known currencies (default EUR for Spuerkeess/Revolut sandbox).
    accs = await db.linked_accounts.find(
        {"user_id": user["id"], "is_active": True}, {"_id": 0}
    ).to_list(10)
    linked_currencies = {(a.get("primary_currency") or "EUR") for a in accs}
    if currency not in linked_currencies:
        raise HTTPException(
            400,
            f"Destination currency {currency} doesn't match user currency or any linked account.",
        )


@api.get("/destinations", response_model=List[SavingsDestinationOut])
async def list_destinations(user=Depends(current_user)):
    rows = await db.savings_destinations.find(
        {"user_id": user["id"], "is_active": True}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return [to_dest_out(r) for r in rows]


@api.post("/destinations", response_model=SavingsDestinationOut, status_code=201)
async def create_destination(data: SavingsDestinationIn, user=Depends(current_user)):
    await _validate_destination_currency(user, data.currency)
    did = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "id": did, "user_id": user["id"], **data.model_dump(),
        "is_active": True, "created_at": now,
    }
    if data.is_default:
        await db.savings_destinations.update_many(
            {"user_id": user["id"]}, {"$set": {"is_default": False}}
        )
    await db.savings_destinations.insert_one(doc)
    return to_dest_out(doc)


@api.patch("/destinations/{did}", response_model=SavingsDestinationOut)
async def update_destination(did: str, data: SavingsDestinationIn, user=Depends(current_user)):
    await _validate_destination_currency(user, data.currency)
    existing = await db.savings_destinations.find_one({"id": did, "user_id": user["id"]})
    if not existing:
        raise HTTPException(404, "Destination not found")
    if data.is_default:
        await db.savings_destinations.update_many(
            {"user_id": user["id"], "id": {"$ne": did}}, {"$set": {"is_default": False}}
        )
    await db.savings_destinations.update_one(
        {"id": did, "user_id": user["id"]}, {"$set": data.model_dump()}
    )
    fresh = await db.savings_destinations.find_one({"id": did}, {"_id": 0})
    return to_dest_out(fresh)


@api.delete("/destinations/{did}")
async def delete_destination(did: str, user=Depends(current_user)):
    d = await db.savings_destinations.find_one({"id": did, "user_id": user["id"]})
    if not d:
        raise HTTPException(404, "Destination not found")
    if d.get("is_default") and d.get("is_active"):
        # Promote another active destination to default before disabling.
        other = await db.savings_destinations.find_one(
            {"user_id": user["id"], "id": {"$ne": did}, "is_active": True}
        )
        if other:
            await db.savings_destinations.update_one(
                {"id": other["id"]}, {"$set": {"is_default": True}}
            )
    await db.savings_destinations.update_one(
        {"id": did, "user_id": user["id"]}, {"$set": {"is_active": False, "is_default": False}}
    )
    return {"ok": True}


async def _get_default_destination(user_id: str) -> Optional[dict]:
    d = await db.savings_destinations.find_one(
        {"user_id": user_id, "is_default": True, "is_active": True}, {"_id": 0}
    )
    if d:
        return d
    return await db.savings_destinations.find_one(
        {"user_id": user_id, "is_active": True}, {"_id": 0}
    )


# ---------- Bank linking ----------
def _revolut_callback_url(request: Request) -> str:
    if REVOLUT_REDIRECT_FALLBACK:
        return REVOLUT_REDIRECT_FALLBACK
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/bank/revolut/callback"


def _revolut_consent_url(state: str, redirect_uri: str) -> str:
    return f"{REVOLUT_AUTH_URL}?{urlencode({'client_id': REVOLUT_CLIENT_ID, 'response_type': 'code', 'scope': 'accounts', 'redirect_uri': redirect_uri, 'state': state})}"


@api.post("/bank/link", response_model=LinkedAccountOut, status_code=201)
async def link_bank(data: LinkedAccountIn, request: Request, user=Depends(current_user)):
    await db.linked_accounts.update_many(
        {"user_id": user["id"], "provider": data.provider, "is_active": True},
        {"$set": {"is_active": False}},
    )
    aid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    if data.provider == "revolut" and not data.access_token:
        state = uuid.uuid4().hex
        redirect_uri = _revolut_callback_url(request)
        doc = {
            "id": aid, "user_id": user["id"], "provider": "revolut",
            "access_token": "", "refresh_token": None, "token_expires_at": None,
            "is_active": False, "oauth_state": state, "redirect_uri": redirect_uri,
            "linked_at": now, "connected_at": None, "primary_currency": "EUR",
        }
        await db.linked_accounts.insert_one(doc)
        return LinkedAccountOut(
            id=aid, provider="revolut", is_active=False, linked_at=now,
            connected_at=None, consent_url=_revolut_consent_url(state, redirect_uri),
        )

    doc = {
        "id": aid, "user_id": user["id"], "provider": data.provider,
        "access_token": data.access_token or "stub",
        "refresh_token": None, "token_expires_at": None,
        "is_active": True, "oauth_state": None,
        "linked_at": now, "connected_at": now,
        "primary_currency": "EUR",
    }
    await db.linked_accounts.insert_one(doc)
    return LinkedAccountOut(
        id=aid, provider=data.provider, is_active=True, linked_at=now,
        connected_at=now, consent_url=None,
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
            connected_at=ensure_aware(r["connected_at"]) if r.get("connected_at") else None,
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
            "connected_at": datetime.now(timezone.utc),
        }},
    )
    return HTMLResponse(_callback_page("All set — you can close this window and return to Éva.", success=True))


def _callback_page(msg: str, success: bool = False) -> str:
    color = "#7B8C73" if success else "#C27D72"
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
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": redirect_uri or "", "client_id": REVOLUT_CLIENT_ID},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15,
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
            data={"grant_type": "refresh_token", "refresh_token": refresh_token,
                  "client_id": REVOLUT_CLIENT_ID},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=15,
        )
    except requests.RequestException as e:
        raise HTTPException(502, f"Refresh endpoint unreachable: {e}")
    if resp.status_code == 401:
        raise HTTPException(401, "Refresh token rejected")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Refresh error {resp.status_code}")
    return resp.json()


# ---------- Sync ----------
def _fetch_revolut_personal(token: str) -> list:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        resp = requests.get(f"{REVOLUT_API_BASE}/transactions", headers=headers, timeout=15)
    except requests.RequestException as e:
        raise HTTPException(502, f"Revolut unreachable: {e}")
    if resp.status_code == 401:
        raise HTTPException(401, "Revolut token rejected")
    if resp.status_code >= 400:
        raise HTTPException(502, f"Revolut error {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        return []
    if isinstance(body, list):
        return body
    return body.get("Data", {}).get("Transaction") or body.get("transactions") or []


def _parse_revolut(items: list) -> list:
    out = []
    for it in items:
        provider_id = it.get("TransactionId") or it.get("id") or it.get("transaction_id")
        if not provider_id:
            continue
        merch = None
        md = it.get("MerchantDetails")
        if isinstance(md, dict):
            merch = md.get("MerchantName")
        if not merch and isinstance(it.get("merchant"), dict):
            merch = it["merchant"].get("name")
        merch = merch or it.get("TransactionInformation") or it.get("description") or "Unknown"

        amount = 0.0
        currency = "EUR"
        amt_obj = it.get("Amount")
        if isinstance(amt_obj, dict):
            amount = float(amt_obj.get("Amount") or 0.0)
            currency = amt_obj.get("Currency") or "EUR"
            if (it.get("CreditDebitIndicator") or "").lower() == "debit":
                amount = -abs(amount)
            elif (it.get("CreditDebitIndicator") or "").lower() == "credit":
                amount = abs(amount)
        else:
            amount = float(it.get("amount") or 0.0)
            currency = it.get("currency") or "EUR"
        if amount >= 0:
            continue

        ts_raw = (it.get("BookingDateTime") or it.get("ValueDateTime")
                  or it.get("completed_at") or it.get("created_at"))
        try:
            ts = datetime.fromisoformat((ts_raw or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            ts = datetime.now(timezone.utc)

        # Source: prefer AccountId, fall back to card last4 or "unknown"
        source_id = it.get("AccountId") or (it.get("account") or {}).get("id") or it.get("source_id")
        source_label = (it.get("AccountName") or
                        (it.get("account") or {}).get("name") or
                        f"Revolut · {currency}")
        source_type = "account"
        if it.get("CardId") or it.get("card_id"):
            source_type = "card"
            source_id = source_id or it.get("CardId") or it.get("card_id")
        if (it.get("PocketId") or it.get("pocket_id") or
                (md or {}).get("PocketId")):
            source_type = "pocket"

        out.append({
            "provider_txn_id": str(provider_id),
            "merchant_name": str(merch),
            "amount": abs(amount),
            "currency": currency,
            "transacted_at": ts,
            "source_account_id": str(source_id) if source_id else None,
            "source_label": source_label,
            "source_type": source_type,
            "source_currency": currency,
        })
    return out


async def _refresh_revolut_if_needed(acc: dict) -> str:
    token = acc.get("access_token") or ""
    expires_at = acc.get("token_expires_at")
    if not expires_at or not acc.get("refresh_token"):
        return token
    expires_at = ensure_aware(expires_at)
    if datetime.now(timezone.utc) < expires_at - timedelta(seconds=60):
        return token
    fresh = await run_in_threadpool(_revolut_refresh, acc["refresh_token"])
    new_access = fresh.get("access_token") or ""
    new_refresh = fresh.get("refresh_token") or acc["refresh_token"]
    new_exp = datetime.now(timezone.utc) + timedelta(seconds=int(fresh.get("expires_in") or 3600))
    await db.linked_accounts.update_one(
        {"id": acc["id"]},
        {"$set": {"access_token": new_access, "refresh_token": new_refresh, "token_expires_at": new_exp}},
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
    skipped_retroactive = 0
    for acc in accounts:
        connected_at = ensure_aware(acc.get("connected_at") or acc.get("linked_at"))
        provider = acc["provider"]
        if provider == "revolut":
            token = await _refresh_revolut_if_needed(acc)
            raw = await run_in_threadpool(_fetch_revolut_personal, token)
            items = _parse_revolut(raw)
        else:
            items = _stub_spuerkeess(connected_at)

        for it in items:
            # NO RETROACTIVE TAXATION — ignore transactions at/before account connection time.
            tx_ts = ensure_aware(it["transacted_at"])
            if tx_ts <= connected_at:
                skipped_retroactive += 1
                continue

            existing = await db.raw_transactions.find_one({
                "user_id": user["id"], "account_id": acc["id"],
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
                "transacted_at": tx_ts,
                "ingested_at": datetime.now(timezone.utc),
                "matched_category_id": None,
                "status": "pending",
                "source_account_id": it.get("source_account_id"),
                "source_label": it.get("source_label"),
                "source_type": it.get("source_type") or "unknown",
                "source_currency": it.get("source_currency") or it["currency"],
            })
            ingested += 1

    return {
        "ingested": ingested,
        "duplicates": skipped_duplicates,
        "skipped_retroactive": skipped_retroactive,
        "accounts": len(accounts),
    }


# ---------- Tax engine ----------
def _match_category(merchant: str, cats: list, profile_type: str = "balanced", apply_ethical_penalty_all_profiles: bool = False) -> Optional[dict]:
    name = (merchant or "").lower()
    is_ethical_mode = (profile_type == "ethical") or apply_ethical_penalty_all_profiles
    if is_ethical_mode:
        ordered = sorted(cats, key=lambda c: 0 if c.get("name") == "Ethical Penalty" else 1)
    else:
        ordered = sorted(cats, key=lambda c: 1 if c.get("name") == "Ethical Penalty" else 0)
        
    for cat in ordered:
        for kw in cat.get("merchant_keywords") or []:
            if kw and kw.lower() in name:
                return cat
    return None

async def _execute_transfers(user: dict, trigger: str = "manual") -> List[dict]:
    """
    Group eligible tax_events (pending events, no requires_review, with source and destination)
    by (source_account_id, destination_id), simulate a transfer per group, write tax_transfers
    rows, and mark events transferred/executed.

    Returns a list of per-group summaries.
    """
    pending = await db.tax_events.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    ).to_list(2000)
    if not pending:
        return []

    groups: dict = {}
    for ev in pending:
        if ev.get("requires_review") or ev.get("transfer_status") == "requires_review":
            continue
        if not ev.get("source_account_id") or not ev.get("destination_id"):
            continue
        key = (ev["source_account_id"], ev["destination_id"])
        groups.setdefault(key, []).append(ev)

    out = []
    for (src, dest), events in groups.items():
        total = round(sum(float(e["tax_amount"]) for e in events), 2)
        ref = f"sim_{uuid.uuid4().hex[:12]}"
        transfer_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        first = events[0]
        await db.tax_transfers.insert_one({
            "id": transfer_id,
            "user_id": user["id"],
            "source_account_id": src,
            "source_label": first.get("source_label"),
            "destination_id": dest,
            "destination_label": first.get("destination_label"),
            "destination_currency": first.get("destination_currency"),
            "tax_event_ids": [e["id"] for e in events],
            "total_amount": total,
            "status": "simulated",
            "provider_ref": ref,
            "executed_at": now,
            "trigger": trigger,
        })
        await db.tax_events.update_many(
            {"id": {"$in": [e["id"] for e in events]}},
            {"$set": {
                "status": "transferred",
                "transfer_status": "executed",
                "transfer_id": transfer_id,
                "transfer_provider_ref": ref,
            }},
        )
        if user.get("expo_push_token"):
            label = first.get("category_name") or "your spending"
            if len(events) == 1:
                msg = f"€{total:.2f} saved on {label}"
            else:
                msg = f"€{total:.2f} saved across {len(events)} taxed transactions"
            send_push(user["expo_push_token"], "Tax applied", msg)

        out.append({
            "transfer_id": transfer_id, "provider_ref": ref,
            "total_amount": total, "event_count": len(events),
            "source_account_id": src, "destination_id": dest,
            "status": "executed",
        })
    return out


async def _maybe_auto_transfer(user: dict):
    """Savings-Beast: when pending > €5 after process, fire transfers immediately."""
    if user.get("profile_type") != "savings_beast":
        return None
    pending = await db.tax_events.find(
        {"user_id": user["id"], "status": "pending"}, {"_id": 0}
    ).to_list(1000)
    total = round(sum(float(e["tax_amount"]) for e in pending), 2)
    if total <= SAVINGS_BEAST_TRIGGER_AMOUNT or not pending:
        return None
    results = await _execute_transfers(user, trigger="savings_beast_auto")
    if not results:
        return None
    return {
        "transferred": sum(r["event_count"] for r in results),
        "total_amount": round(sum(r["total_amount"] for r in results), 2),
        "transfers": results,
    }


async def _maybe_instant_transfer(user: dict):
    if user.get("transfer_frequency", "instant") != "instant":
        return None
    results = await _execute_transfers(user, trigger="instant")
    if not results:
        return None
    await db.users.update_one(
        {"id": user["id"]}, {"$set": {"transfer_last_run_at": datetime.now(timezone.utc)}}
    )
    return {
        "transferred": sum(r["event_count"] for r in results),
        "total_amount": round(sum(r["total_amount"] for r in results), 2),
        "transfers": results,
    }


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
    apply_ethical = user.get("apply_ethical_penalty_all_profiles", False)
    destination = await _get_default_destination(user["id"])

    taxed = 0
    skipped = 0
    unmatched = 0
    review = 0
    taxed_details = []

    for tx in pending:
        cat = _match_category(
            tx["merchant_name"], 
            cats, 
            profile_type=profile, 
            apply_ethical_penalty_all_profiles=apply_ethical
        )
        if not cat:
            await db.raw_transactions.update_one(
                {"id": tx["id"]}, {"$set": {"status": "unmatched", "matched_category_id": None}},
            )
            unmatched += 1
            continue

        today_iso = ensure_aware(tx["transacted_at"]).date().isoformat()
        counter_key = {"user_id": user["id"], "category_id": cat["id"], "counter_date": today_iso}
        counter = await db.daily_repetition_counters.find_one(counter_key)
        hit_count = counter["hit_count"] if counter else 0

        day_start = ensure_aware(tx["transacted_at"]).replace(hour=0, minute=0, second=0, microsecond=0)
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
                {"id": tx["id"]}, {"$set": {"status": "skipped", "matched_category_id": cat["id"]}},
            )
            skipped += 1
            continue

        base = float(cat["tax_rate"])
        inc = float(cat.get("rep_increment", 0.05))
        max_rate = float(cat.get("max_tax_rate", 0.50))
        rep_rate = min(max_rate, base + hit_count * inc)
        effective_rate = apply_profile_multiplier(rep_rate, cat["name"], profile, max_rate, user.get("apply_ethical_penalty_all_profiles", False))
        tax_amount = round(float(tx["amount"]) * effective_rate, 2)
        if taxed_today + tax_amount > cap:
            tax_amount = round(max(0.0, cap - taxed_today), 2)
        if tax_amount <= 0:
            await db.raw_transactions.update_one(
                {"id": tx["id"]}, {"$set": {"status": "skipped", "matched_category_id": cat["id"]}},
            )
            skipped += 1
            continue

        # Source / destination resolution.
        src_id = tx.get("source_account_id")
        src_label = tx.get("source_label")
        src_type = tx.get("source_type") or "unknown"
        src_ccy = tx.get("source_currency") or tx.get("currency") or "EUR"
        dest_id = destination["id"] if destination else None
        dest_label = destination["label"] if destination else None
        dest_ccy = destination["currency"] if destination else None

        requires_review = False
        review_reason = None
        if not src_id:
            requires_review, review_reason = True, "unknown_source"
        elif not destination:
            requires_review, review_reason = True, "no_destination"
        elif dest_ccy and src_ccy and dest_ccy != src_ccy:
            requires_review, review_reason = True, "currency_mismatch"

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
            # Source / destination tracking
            "source_account_id": src_id,
            "source_label": src_label,
            "source_type": src_type,
            "source_currency": src_ccy,
            "destination_id": dest_id,
            "destination_label": dest_label,
            "destination_currency": dest_ccy,
            "transfer_status": "requires_review" if requires_review else "pending",
            "transfer_id": None,
            "transfer_provider_ref": None,
            "requires_review": requires_review,
            "review_reason": review_reason,
        })
        if counter:
            await db.daily_repetition_counters.update_one(
                {"id": counter["id"]}, {"$inc": {"hit_count": 1}}
            )
        else:
            await db.daily_repetition_counters.insert_one(
                {"id": str(uuid.uuid4()), **counter_key, "hit_count": 1}
            )
        if default_bucket_id:
            await db.buckets.update_one(
                {"id": default_bucket_id, "user_id": user["id"]},
                [{"$set": {
                    "saved_amount": {
                        "$max": [0.0, {"$subtract": ["$saved_amount", float(tax_amount)]}]
                    }
                }}]
            )
        await db.raw_transactions.update_one(
            {"id": tx["id"]}, {"$set": {"status": "taxed", "matched_category_id": cat["id"]}},
        )
        taxed += 1
        taxed_details.append({
            "merchant_name": tx["merchant_name"],
            "category_name": cat["name"],
            "tax_amount": tax_amount,
        })
        if requires_review:
            review += 1

    result = {
        "processed": len(pending), "taxed": taxed,
        "skipped": skipped, "unmatched": unmatched,
        "requires_review": review,
        "taxed_details": taxed_details
    }

    auto = await _maybe_auto_transfer(user)
    if auto:
        result["auto_transfer"] = auto
    # Re-read user (savings_beast may have refreshed timestamps).
    user = await db.users.find_one({"id": user["id"]}, {"_id": 0}) or user
    instant = await _maybe_instant_transfer(user)
    if instant and not auto:
        result["instant_transfer"] = instant
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
        bucket_id = ev["bucket_id"]
        tax_amount = float(ev.get("tax_amount", 0))
        await db.buckets.update_one(
            {"id": bucket_id, "user_id": user["id"]},
            [{"$set": {
                "saved_amount": {
                    "$max": [0.0, {"$subtract": ["$saved_amount", tax_amount]}]
                }
            }}]
        )
    return {"ok": True}


@api.post("/tax/transfer")
async def tax_transfer(user=Depends(current_user)):
    """Manual trigger — group eligible pending events and execute simulated transfers."""
    results = await _execute_transfers(user, trigger="manual")
    if not results:
        return {"transferred": 0, "total_amount": 0.0, "transfers": []}
    return {
        "transferred": sum(r["event_count"] for r in results),
        "total_amount": round(sum(r["total_amount"] for r in results), 2),
        "transfers": results,
    }


# ---------- Scheduler ----------
async def _run_scheduler_once():
    """One pass — process users whose scheduled transfer is due."""
    now = datetime.now(timezone.utc)
    users = await db.users.find(
        {"transfer_frequency": {"$in": ["daily", "weekly"]}, "pause_all_taxes": {"$ne": True}},
        {"_id": 0},
    ).to_list(10000)
    fired = []
    for u in users:
        freq = u.get("transfer_frequency")
        last = u.get("transfer_last_run_at")
        interval = timedelta(days=1) if freq == "daily" else timedelta(days=7)
        if last and ensure_aware(last) + interval > now:
            continue
        results = await _execute_transfers(u, trigger=f"scheduler_{freq}")
        await db.users.update_one(
            {"id": u["id"]}, {"$set": {"transfer_last_run_at": now}}
        )
        if results:
            fired.append({"user_id": u["id"], "frequency": freq, "transfers": results})
    return fired


@api.post("/scheduler/run")
async def scheduler_run_manual(user=Depends(current_user)):
    """Manual scheduler trigger (debug/test). Only runs for the current user."""
    if user.get("transfer_frequency") in ("daily", "weekly") and not user.get("pause_all_taxes"):
        results = await _execute_transfers(user, trigger=f"scheduler_{user['transfer_frequency']}_manual")
        await db.users.update_one(
            {"id": user["id"]}, {"$set": {"transfer_last_run_at": datetime.now(timezone.utc)}}
        )
        return {"ok": True, "transfers": results}
    # Even for instant frequency, allow manual run to flush pending.
    results = await _execute_transfers(user, trigger="scheduler_manual")
    return {"ok": True, "transfers": results}

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
                source_account_id=ev.get("source_account_id") or r.get("source_account_id"),
                source_label=ev.get("source_label") or r.get("source_label"),
                source_type=ev.get("source_type") or r.get("source_type"),
                source_currency=ev.get("source_currency") or r.get("source_currency"),
                destination_id=ev.get("destination_id"),
                destination_label=ev.get("destination_label"),
                destination_currency=ev.get("destination_currency"),
                transfer_status=ev.get("transfer_status"),
                transfer_provider_ref=ev.get("transfer_provider_ref"),
                requires_review=bool(ev.get("requires_review", False)),
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
                source_account_id=r.get("source_account_id"),
                source_label=r.get("source_label"),
                source_type=r.get("source_type"),
                source_currency=r.get("source_currency"),
            ))
    return out


# ---------- Insights ----------
@api.get("/insights/summary")
async def insights_summary(user=Depends(current_user)):
    base_match = {"user_id": user["id"], "status": {"$in": ["pending", "transferred"]}}
    agg = await db.tax_events.aggregate([
        {"$match": base_match},
        {"$group": {"_id": None,
                    "total_taxed": {"$sum": "$tax_amount"},
                    "total_spent": {"$sum": "$original_amount"},
                    "count": {"$sum": 1}}},
    ]).to_list(1)
    totals = agg[0] if agg else {"total_spent": 0, "total_taxed": 0, "count": 0}

    by_cat = await db.tax_events.aggregate([
        {"$match": base_match},
        {"$group": {"_id": "$category_name",
                    "spent": {"$sum": "$original_amount"},
                    "taxed": {"$sum": "$tax_amount"},
                    "count": {"$sum": 1}}},
        {"$sort": {"spent": -1}},
    ]).to_list(100)

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    by_day = await db.tax_events.aggregate([
        {"$match": {**base_match, "created_at": {"$gte": week_ago}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "spent": {"$sum": "$original_amount"},
                    "taxed": {"$sum": "$tax_amount"}}},
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
        "by_category": [{"name": r["_id"], "spent": round(r["spent"], 2),
                         "taxed": round(r["taxed"], 2), "count": r["count"]} for r in by_cat],
        "by_day": [{"date": r["_id"], "spent": round(r["spent"], 2),
                    "taxed": round(r["taxed"], 2)} for r in by_day],
        "streak_days_no_impulse": days_since,
        "profile_type": user.get("profile_type", "balanced"),
    }


# ---------- Monthly resume ----------
def _month_bounds(year: int, month: int):
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


async def _monthly_data(user: dict, year: int, month: int):
    start, end = _month_bounds(year, month)
    match = {"user_id": user["id"], "transacted_at": {"$gte": start, "$lt": end}}

    events = await db.tax_events.find(match, {"_id": 0}).sort("transacted_at", 1).to_list(5000)

    total_spent = sum(float(e.get("original_amount", 0)) for e in events
                      if e.get("status") != "overridden")
    total_taxed = sum(float(e.get("tax_amount", 0)) for e in events
                      if e.get("status") != "overridden")
    overridden_count = sum(1 for e in events if e.get("status") == "overridden")
    review_count = sum(1 for e in events if e.get("requires_review"))

    by_category: dict = {}
    by_profile: dict = {}
    by_destination: dict = {}
    by_status: dict = {}
    for e in events:
        cat = e.get("category_name", "Unknown")
        prof = e.get("profile_applied", "balanced")
        dest = e.get("destination_label", "—")
        tax_status = e.get("transfer_status", "pending")
        amount = 0.0 if e.get("status") == "overridden" else float(e.get("tax_amount", 0))
        by_category[cat] = by_category.get(cat, 0.0) + amount
        by_profile[prof] = by_profile.get(prof, 0.0) + amount
        by_destination[dest] = by_destination.get(dest, 0.0) + amount
        by_status[tax_status] = by_status.get(tax_status, 0) + 1

    return {
        "year": year, "month": month,
        "totals": {
            "spent": round(total_spent, 2),
            "taxed": round(total_taxed, 2),
            "events": len(events),
            "overridden": overridden_count,
            "requires_review": review_count,
        },
        "by_category": [{"name": k, "taxed": round(v, 2)} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
        "by_profile": [{"name": k, "taxed": round(v, 2)} for k, v in sorted(by_profile.items(), key=lambda x: -x[1])],
        "by_destination": [{"label": k, "taxed": round(v, 2)} for k, v in sorted(by_destination.items(), key=lambda x: -x[1])],
        "by_transfer_status": [{"status": k, "count": v} for k, v in by_status.items()],
        "events": [
            {
                "transacted_at": ensure_aware(e["transacted_at"]).isoformat(),
                "merchant": e_get_merchant(e),
                "category": e.get("category_name"),
                "original_amount": float(e.get("original_amount", 0)),
                "currency": e.get("source_currency", "EUR"),
                "profile": e.get("profile_applied"),
                "tax_rate": round(float(e.get("tax_rate_applied", 0)), 4),
                "tax_amount": float(e.get("tax_amount", 0)),
                "source_label": e.get("source_label"),
                "destination_label": e.get("destination_label"),
                "transfer_status": e.get("transfer_status"),
                "transfer_provider_ref": e.get("transfer_provider_ref"),
                "status": e.get("status"),
            }
            for e in events
        ],
    }


def e_get_merchant(event: dict) -> Optional[str]:
    # Tax events don't store merchant directly; surface it via the join when available.
    # Caller will replace this with raw_tx merchant if needed.
    return event.get("merchant_name")


@api.get("/reports/monthly")
async def reports_monthly(user: dict, year: int, month: int):
    if month < 1 or month > 12:
        raise HTTPException(400, "month must be 1..12")
    data = await _monthly_data(user, year, month)
    # Enrich events with merchant_name from raw_transactions.
    raw_ids = [ev for ev in await db.tax_events.find(
        {"user_id": user["id"]}, {"_id": 0, "raw_txn_id": 1}
    ).to_list(5000)]
    rid_map = {}
    if data["events"]:
        # Pull merchants in one query
        raw_txns = await db.raw_transactions.find(
            {"user_id": user["id"]}, {"_id": 0, "id": 1, "merchant_name": 1}
        ).to_list(5000)
        rid_map = {r["id"]: r["merchant_name"] for r in raw_txns}
        # Match by raw_txn_id stored on the tax_event document
        tax_evs = await db.tax_events.find(
            {"user_id": user["id"]}, {"_id": 0, "id": 1, "raw_txn_id": 1}
        ).to_list(5000)
        ev_to_raw = {e["id"]: e.get("raw_txn_id") for e in tax_evs}
        # We don't have event_id in the projection above; re-pull by transacted_at order.
        # Simpler: rebuild events list using the same query as _monthly_data.
        start, end = _month_bounds(year, month)
        full_evs = await db.tax_events.find(
            {"user_id": user["id"], "transacted_at": {"$gte": start, "$lt": end}}, {"_id": 0}
        ).sort("transacted_at", 1).to_list(5000)
        data["events"] = [
            {
                **{
                    "transacted_at": ensure_aware(e["transacted_at"]).isoformat(),
                    "merchant": rid_map.get(e.get("raw_txn_id"), "Unknown"),
                    "category": e.get("category_name"),
                    "original_amount": float(e.get("original_amount", 0)),
                    "currency": e.get("source_currency", "EUR"),
                    "profile": e.get("profile_applied"),
                    "tax_rate": round(float(e.get("tax_rate_applied", 0)), 4),
                    "tax_amount": float(e.get("tax_amount", 0)),
                    "source_label": e.get("source_label"),
                    "destination_label": e.get("destination_label"),
                    "transfer_status": e.get("transfer_status"),
                    "transfer_provider_ref": e.get("transfer_provider_ref"),
                    "status": e.get("status"),
                }
            }
            for e in full_evs
        ]
    return data


@api.get("/reports/monthly/export.csv")
async def reports_monthly_csv(year: int, month: int, user=Depends(current_user)):
    if month < 1 or month > 12:
        raise HTTPException(400, "month must be 1..12")
    data = await reports_monthly(year, month, user=user)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "transacted_at", "merchant", "category", "amount", "currency",
        "profile", "tax_rate", "tax_amount", "source_label",
        "destination_label", "transfer_status", "transfer_provider_ref", "status",
    ])
    for e in data["events"]:
        writer.writerow([
            e["transacted_at"], e["merchant"], e["category"],
            f"{e['original_amount']:.2f}", e["currency"],
            e["profile"], f"{e['tax_rate']:.4f}", f"{e['tax_amount']:.2f}",
            e["source_label"] or "", e["destination_label"] or "",
            e["transfer_status"] or "", e["transfer_provider_ref"] or "", e["status"] or "",
        ])
    csv_bytes = buf.getvalue().encode("utf-8")
    fname = f"eva_resume_{year}-{month:02d}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------- Wiring ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
