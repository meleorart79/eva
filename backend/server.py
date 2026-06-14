import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)

app = FastAPI(title="Eva — Behavior Tax")
api = APIRouter(prefix="/api")

ALLOWED_CURRENCIES = ["EUR", "USD", "GBP"]

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


class TransactionIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0)
    category_id: str
    note: Optional[str] = None
    bucket_id: Optional[str] = None  # defaults to user's default bucket


class TransactionOut(BaseModel):
    id: str
    merchant: str
    amount: float
    category_id: str
    category_name: str
    tax_rate: float
    tax_amount: float
    bucket_id: str
    bucket_name: str
    note: Optional[str] = None
    created_at: datetime


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


def to_user_out(u: dict) -> UserOut:
    return UserOut(
        id=u["id"], email=u["email"], name=u["name"],
        currency=u["currency"], default_bucket_id=u.get("default_bucket_id"),
    )


DEFAULT_CATEGORIES = [
    {"name": "Coffee", "icon": "coffee", "tax_rate": 0.25},
    {"name": "Fast Food", "icon": "utensils", "tax_rate": 0.30},
    {"name": "Groceries", "icon": "shopping-cart", "tax_rate": 0.05},
    {"name": "Clothes", "icon": "shopping-bag", "tax_rate": 0.15},
    {"name": "Entertainment", "icon": "film", "tax_rate": 0.20},
    {"name": "Transport", "icon": "car", "tax_rate": 0.10},
    {"name": "Other", "icon": "tag", "tax_rate": 0.10},
]


async def seed_user_defaults(user_id: str) -> str:
    for c in DEFAULT_CATEGORIES:
        await db.categories.insert_one({
            "id": str(uuid.uuid4()), "user_id": user_id, **c,
        })
    bucket_id = str(uuid.uuid4())
    await db.buckets.insert_one({
        "id": bucket_id, "user_id": user_id,
        "name": "Travel Fund", "target_amount": 2000.0,
        "saved_amount": 0.0, "image_key": "travel", "is_default": True,
        "created_at": datetime.now(timezone.utc),
    })
    return bucket_id


# ---------- Routes ----------
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
    token = create_token(uid)
    return Token(access_token=token, user=to_user_out(user_doc))


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
    if update:
        await db.users.update_one({"id": user["id"]}, {"$set": update})
        user.update(update)
    return to_user_out(user)


# Categories
@api.get("/categories", response_model=List[CategoryOut])
async def list_categories(user=Depends(current_user)):
    rows = await db.categories.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    return [CategoryOut(id=r["id"], name=r["name"], icon=r["icon"], tax_rate=r["tax_rate"]) for r in rows]


@api.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryIn, user=Depends(current_user)):
    cid = str(uuid.uuid4())
    await db.categories.insert_one({"id": cid, "user_id": user["id"], **data.dict()})
    return CategoryOut(id=cid, **data.dict())


@api.patch("/categories/{cid}", response_model=CategoryOut)
async def update_category(cid: str, data: CategoryIn, user=Depends(current_user)):
    res = await db.categories.update_one(
        {"id": cid, "user_id": user["id"]}, {"$set": data.dict()}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Category not found")
    return CategoryOut(id=cid, **data.dict())


@api.delete("/categories/{cid}")
async def delete_category(cid: str, user=Depends(current_user)):
    await db.categories.delete_one({"id": cid, "user_id": user["id"]})
    return {"ok": True}


# Buckets
@api.get("/buckets", response_model=List[BucketOut])
async def list_buckets(user=Depends(current_user)):
    rows = await db.buckets.find({"user_id": user["id"]}, {"_id": 0}).to_list(200)
    return [
        BucketOut(
            id=r["id"], name=r["name"], target_amount=r["target_amount"],
            saved_amount=r.get("saved_amount", 0.0), image_key=r.get("image_key", "travel"),
            is_default=r.get("is_default", False),
        )
        for r in rows
    ]


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
    return BucketOut(id=bid, name=data.name, target_amount=data.target_amount,
                     saved_amount=0.0, image_key=data.image_key, is_default=data.is_default)


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
    return BucketOut(
        id=b["id"], name=b["name"], target_amount=b["target_amount"],
        saved_amount=b.get("saved_amount", 0.0), image_key=b.get("image_key", "travel"),
        is_default=b.get("is_default", False),
    )


@api.delete("/buckets/{bid}")
async def delete_bucket(bid: str, user=Depends(current_user)):
    b = await db.buckets.find_one({"id": bid, "user_id": user["id"]})
    if not b:
        raise HTTPException(404, "Bucket not found")
    if b.get("is_default"):
        raise HTTPException(400, "Cannot delete the default bucket")
    await db.buckets.delete_one({"id": bid, "user_id": user["id"]})
    return {"ok": True}


# Transactions
@api.get("/transactions", response_model=List[TransactionOut])
async def list_transactions(limit: int = 100, user=Depends(current_user)):
    rows = await db.transactions.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return [
        TransactionOut(
            id=r["id"], merchant=r["merchant"], amount=r["amount"],
            category_id=r["category_id"], category_name=r["category_name"],
            tax_rate=r["tax_rate"], tax_amount=r["tax_amount"],
            bucket_id=r["bucket_id"], bucket_name=r["bucket_name"],
            note=r.get("note"), created_at=r["created_at"],
        )
        for r in rows
    ]


@api.post("/transactions", response_model=TransactionOut, status_code=201)
async def create_transaction(data: TransactionIn, user=Depends(current_user)):
    cat = await db.categories.find_one({"id": data.category_id, "user_id": user["id"]})
    if not cat:
        raise HTTPException(404, "Category not found")

    bucket_id = data.bucket_id or user.get("default_bucket_id")
    bucket = await db.buckets.find_one({"id": bucket_id, "user_id": user["id"]})
    if not bucket:
        raise HTTPException(404, "Bucket not found")

    tax_rate = float(cat["tax_rate"])
    tax_amount = round(data.amount * tax_rate, 2)

    tx_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc = {
        "id": tx_id, "user_id": user["id"], "merchant": data.merchant,
        "amount": data.amount, "category_id": cat["id"], "category_name": cat["name"],
        "tax_rate": tax_rate, "tax_amount": tax_amount,
        "bucket_id": bucket["id"], "bucket_name": bucket["name"],
        "note": data.note, "created_at": now,
    }
    await db.transactions.insert_one(doc)
    await db.buckets.update_one({"id": bucket["id"]}, {"$inc": {"saved_amount": tax_amount}})
    return TransactionOut(
        id=tx_id, merchant=data.merchant, amount=data.amount,
        category_id=cat["id"], category_name=cat["name"],
        tax_rate=tax_rate, tax_amount=tax_amount,
        bucket_id=bucket["id"], bucket_name=bucket["name"],
        note=data.note, created_at=now,
    )


@api.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str, user=Depends(current_user)):
    tx = await db.transactions.find_one({"id": tx_id, "user_id": user["id"]})
    if not tx:
        raise HTTPException(404, "Transaction not found")
    await db.transactions.delete_one({"id": tx_id, "user_id": user["id"]})
    await db.buckets.update_one({"id": tx["bucket_id"]}, {"$inc": {"saved_amount": -tx["tax_amount"]}})
    return {"ok": True}


# Insights
@api.get("/insights/summary")
async def insights_summary(user=Depends(current_user)):
    pipeline = [
        {"$match": {"user_id": user["id"]}},
        {"$group": {
            "_id": None,
            "total_spent": {"$sum": "$amount"},
            "total_taxed": {"$sum": "$tax_amount"},
            "count": {"$sum": 1},
        }},
    ]
    agg = await db.transactions.aggregate(pipeline).to_list(1)
    totals = agg[0] if agg else {"total_spent": 0, "total_taxed": 0, "count": 0}

    # By category
    by_cat = await db.transactions.aggregate([
        {"$match": {"user_id": user["id"]}},
        {"$group": {
            "_id": "$category_name",
            "spent": {"$sum": "$amount"},
            "taxed": {"$sum": "$tax_amount"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"spent": -1}},
    ]).to_list(100)

    # Last 7 days
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    week_pipeline = [
        {"$match": {"user_id": user["id"], "created_at": {"$gte": week_ago}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "spent": {"$sum": "$amount"},
            "taxed": {"$sum": "$tax_amount"},
        }},
        {"$sort": {"_id": 1}},
    ]
    by_day = await db.transactions.aggregate(week_pipeline).to_list(31)

    # Streak: count days since last transaction
    last_tx = await db.transactions.find_one(
        {"user_id": user["id"]}, sort=[("created_at", -1)]
    )
    if last_tx:
        last = last_tx["created_at"]
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        days_since = max(0, (datetime.now(timezone.utc) - last).days)
    else:
        days_since = 0

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
