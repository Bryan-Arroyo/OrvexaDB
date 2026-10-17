from decimal import Decimal

from pydantic import BaseModel

from app.schemas.inventory import MovementView


class DashboardMovementView(MovementView):
    product_name: str
    product_sku: str


class DashboardSummary(BaseModel):
    active_products: int
    active_suppliers: int
    total_stock: Decimal
    low_stock_products: int
    recent_movements: list[DashboardMovementView]
