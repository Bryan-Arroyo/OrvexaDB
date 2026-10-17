from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.core.security import audit, require_permission
from app.db.session import get_db
from app.models.entities import InventoryMovement, Product, User
from app.schemas.inventory import MovementCreate, MovementList, MovementView

router = APIRouter(tags=["inventory"])


@router.get("/inventory-movements", response_model=MovementList)
def list_movements(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), product_id: UUID | None = None, direction: str | None = Query(None, pattern="^(in|out)$"), sort: str = Query("occurred_at", pattern="^(occurred_at|quantity|direction)$"), order: str = Query("desc", pattern="^(asc|desc)$"), db: Session = Depends(get_db), _actor: User = Depends(require_permission("inventory.read"))):
    condition = []
    if product_id:
        condition.append(InventoryMovement.product_id == product_id)
    if direction:
        condition.append(InventoryMovement.direction == direction)
    total = db.scalar(select(func.count()).select_from(InventoryMovement).where(*condition)) or 0
    columns = {"occurred_at": InventoryMovement.occurred_at, "quantity": InventoryMovement.quantity, "direction": InventoryMovement.direction}
    ordering = desc(columns[sort]) if order == "desc" else asc(columns[sort])
    items = db.scalars(select(InventoryMovement).where(*condition).order_by(ordering, InventoryMovement.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return MovementList(items=items, page=page, page_size=page_size, total=total)


@router.post("/inventory-movements", response_model=MovementView, status_code=201)
def create_movement(payload: MovementCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("inventory.move"))):
    product = db.scalar(select(Product).where(Product.id == payload.product_id).with_for_update())
    if product is None:
        raise HTTPException(404, "product not found")
    if not product.is_active:
        raise HTTPException(400, "inactive product")
    quantity = payload.quantity.quantize(Decimal("0.01"))
    new_stock = product.stock_current + quantity if payload.direction == "in" else product.stock_current - quantity
    if new_stock < 0:
        raise HTTPException(409, "insufficient stock")
    movement = InventoryMovement(product_id=product.id, user_id=actor.id, quantity=quantity, direction=payload.direction, reason=payload.reason, description=payload.description)
    product.stock_current = new_stock
    db.add(movement)
    db.flush()
    audit(db, actor, "inventory_movement", "inventory_movement", "success", str(movement.id), metadata={"direction": payload.direction, "quantity": str(quantity), "reason": payload.reason})
    db.commit()
    return movement
