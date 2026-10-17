from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_permission
from app.db.session import get_db
from app.models.entities import InventoryMovement, Product, Supplier, User
from app.schemas.dashboard import DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), _actor: User = Depends(require_permission("inventory.read"))):
    active_products = db.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True))) or 0
    active_suppliers = db.scalar(select(func.count()).select_from(Supplier).where(Supplier.is_active.is_(True))) or 0
    total_stock = db.scalar(select(func.coalesce(func.sum(Product.stock_current), 0)).where(Product.is_active.is_(True))) or 0
    low_stock = db.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True), Product.stock_current <= Product.minimum_stock)) or 0
    recent = db.execute(select(InventoryMovement, Product.name, Product.sku).join(Product, Product.id == InventoryMovement.product_id).order_by(InventoryMovement.occurred_at.desc(), InventoryMovement.id.desc()).limit(10)).all()
    recent_views = [{**movement.__dict__, "product_name": name, "product_sku": sku} for movement, name, sku in recent]
    return DashboardSummary(active_products=active_products, active_suppliers=active_suppliers, total_stock=total_stock, low_stock_products=low_stock, recent_movements=recent_views)
