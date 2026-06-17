from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, EmailStr, Field


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
    access_token: Optional[str] = None


class LinkedAccountOut(BaseModel):
    id: str
    provider: str
    is_active: bool
    linked_at: datetime
    connected_at: Optional[datetime] = None
    consent_url: Optional[str] = None


class SavingsDestinationIn(BaseModel):
    type: Literal["external_iban", "revolut_pocket"]
    label: str = Field(min_length=1, max_length=80)
    identifier: str = Field(min_length=1, max_length=64)
    currency: Literal["EUR", "USD", "GBP"]
    is_default: bool = False


class SavingsDestinationOut(BaseModel):
    id: str
    type: str
    label: str
    identifier: str
    currency: str
    is_default: bool
    is_active: bool
    created_at: datetime


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
    source_account_id: Optional[str] = None
    source_label: Optional[str] = None
    source_type: Optional[str] = None
    source_currency: Optional[str] = None
    destination_id: Optional[str] = None
    destination_label: Optional[str] = None
    destination_currency: Optional[str] = None
    transfer_status: Optional[str] = None
    transfer_provider_ref: Optional[str] = None
    requires_review: bool = False


class SettingsIn(BaseModel):
    profile_type: Optional[Literal["balanced", "aggressive", "ethical", "mindful", "savings_beast"]] = None
    transfer_frequency: Optional[Literal["instant", "daily", "weekly"]] = None
    pause_all_taxes: Optional[bool] = None
    apply_ethical_penalty_all_profiles: Optional[bool] = None


class SettingsOut(BaseModel):
    profile_type: str
    transfer_frequency: str
    pause_all_taxes: bool
    transfer_last_run_at: Optional[datetime] = None
    apply_ethical_penalty_all_profiles: bool


class ResolveReviewIn(BaseModel):
    action: Literal["approve", "change_destination"]
    destination_id: Optional[str] = None


class PushTokenIn(BaseModel):
    token: str
