from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.portfolio import service
from app.domains.portfolio.schemas import PortfolioResponse
from app.models.user import User
from app.security.deps import get_current_user

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
def get_portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """La cartera no depende de la empresa activa: recorre las del usuario."""
    items = service.portfolio(db, user.id)
    return {"items": items, "total": len(items), "limit": len(items), "offset": 0}
