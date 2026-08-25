from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    business_name: str = Field(min_length=1, max_length=255)
    business_type: str | None = Field(default=None, max_length=50)
    initial_cash: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    status: str


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    legal_name: str | None
    tax_id: str | None
    currency: str
    country: str
    timezone: str
    business_type: str | None
    default_tax_rate: Decimal


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead
    organization: OrganizationRead | None = None


class MeResponse(BaseModel):
    user: UserRead
    memberships: list[MembershipRead]
    organizations: list[OrganizationRead]
