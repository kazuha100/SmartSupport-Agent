from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CartItemInput(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=20)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=0, le=20)


class AddressInput(BaseModel):
    recipient: str = Field(min_length=2, max_length=80)
    phone: str = Field(pattern=r"^1\d{10}$")
    province: str = Field(min_length=2, max_length=40)
    city: str = Field(min_length=2, max_length=40)
    detail: str = Field(min_length=5, max_length=300)
    is_default: bool = True


class OrderCreate(BaseModel):
    address_id: str


class SandboxPaymentRequest(BaseModel):
    success: bool = True


class AppealCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    appeal_type: Literal["refund", "return", "repair", "rights_protection"]
    description: str = Field(min_length=10, max_length=2000)


class AppealMaterialRequestInput(BaseModel):
    content: str = Field(min_length=2, max_length=1000)
    due_at: datetime | None = None


class AppealAttachmentReviewInput(BaseModel):
    status: Literal["accepted", "rejected"]
    note: str = Field(default="", max_length=500)


class AppealInvestigationInput(BaseModel):
    responsibility: Literal["merchant", "customer", "logistics", "platform", "undetermined"]
    conclusion: str = Field(min_length=10, max_length=3000)


class AppealProposalInput(BaseModel):
    action: Literal["refund", "return_refund", "replace", "repair", "compensation", "reject"]
    amount_cents: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=10, max_length=2000)


class AppealApprovalInput(BaseModel):
    decision: Literal["approve", "return"]
    comment: str = Field(min_length=2, max_length=1000)


class AppealCustomerFeedbackInput(BaseModel):
    comment: str = Field(default="", max_length=1000)
