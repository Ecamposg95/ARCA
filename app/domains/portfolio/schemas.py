from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class PortfolioItem(BaseModel):
    organization_id: str
    name: str
    tax_id: str | None
    business_type: str | None
    role: str
    cash: Decimal
    receivable: Decimal
    payable_overdue: Decimal
    last_closed_period: str | None  # "AAAA-MM"
    previous_month_closed: bool
    pending_proposals: int
    status: str  # red | amber | green
    reasons: list[str]


class PortfolioResponse(BaseModel):
    items: list[PortfolioItem]
    total: int
    limit: int
    offset: int
