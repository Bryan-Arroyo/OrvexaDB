from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import audit, require_permission
from app.db.session import get_db
from app.models.entities import InventoryMovement, Product, PurchaseOrder, PurchaseOrderLine, Supplier, User
from app.schemas.purchases import PurchaseLineInput, PurchaseLineView, PurchaseOrderInput, PurchaseOrderList, PurchaseOrderView

router = APIRouter(prefix="/purchase-orders", tags=["purchases"])


def _lines(db: Session, order_ids: list[UUID]) -> dict[UUID, list[PurchaseOrderLine]]:
    rows = db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id.in_(order_ids)).order_by(PurchaseOrderLine.id)).all()
    result: dict[UUID, list[PurchaseOrderLine]] = {key: [] for key in order_ids}
    for row in rows:
        result[row.purchase_order_id].append(row)
    return result


def _view(order: PurchaseOrder, lines: list[PurchaseOrderLine]) -> PurchaseOrderView:
    return PurchaseOrderView(
        id=order.id, number=order.order_number, supplier_id=order.supplier_id,
        supplier_name=order.supplier_name, status=order.status, total=order.total,
        created_by=order.created_by, created_at=order.created_at, updated_at=order.updated_at,
        lines=[PurchaseLineView.model_validate(line) for line in lines],
    )


def _validate_lines(db: Session, payload: PurchaseOrderInput) -> tuple[Supplier, list[tuple[PurchaseLineInput, Product]]]:
    supplier = db.scalar(select(Supplier).where(Supplier.id == payload.supplier_id, Supplier.is_active.is_(True)))
    if supplier is None:
        raise HTTPException(400, "active supplier required")
    ids = [line.product_id for line in payload.lines]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "duplicate products are not allowed")
    products = {product.id: product for product in db.scalars(select(Product).where(Product.id.in_(ids), Product.is_active.is_(True))).all()}
    if len(products) != len(ids):
        raise HTTPException(400, "all products must be active")
    return supplier, [(line, products[line.product_id]) for line in payload.lines]


def _make_order(db: Session, payload: PurchaseOrderInput, actor: User) -> PurchaseOrder:
    supplier, product_lines = _validate_lines(db, payload)
    order = PurchaseOrder(order_number=f"PO-{datetime.now(UTC):%Y%m%d}-{uuid4().hex[:12].upper()}", supplier_id=supplier.id, supplier_name=supplier.name, status="draft", created_by=actor.id, total=Decimal("0"))
    db.add(order)
    db.flush()
    total = Decimal("0")
    for line, product in product_lines:
        line_total = (line.quantity * line.unit_cost).quantize(Decimal("0.01"))
        db.add(PurchaseOrderLine(purchase_order_id=order.id, product_id=product.id, product_sku=product.sku, product_name=product.name, quantity=line.quantity, unit_cost=line.unit_cost, line_total=line_total))
        total += line_total
    order.total = total
    return order


@router.get("", response_model=PurchaseOrderList)
def list_orders(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), status: str | None = Query(None, pattern="^(draft|confirmed|received|canceled)$"), db: Session = Depends(get_db), _actor: User = Depends(require_permission("purchase.read"))):
    condition = [PurchaseOrder.status == status] if status else []
    total = db.scalar(select(func.count()).select_from(PurchaseOrder).where(*condition)) or 0
    orders = db.scalars(select(PurchaseOrder).where(*condition).order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    lines = _lines(db, [order.id for order in orders])
    return PurchaseOrderList(items=[_view(order, lines[order.id]) for order in orders], page=page, page_size=page_size, total=total)


@router.get("/{order_id}", response_model=PurchaseOrderView)
def get_order(order_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(require_permission("purchase.read"))):
    order = db.get(PurchaseOrder, order_id)
    if order is None:
        raise HTTPException(404, "purchase order not found")
    return _view(order, _lines(db, [order.id])[order.id])


@router.post("", response_model=PurchaseOrderView, status_code=201)
def create_order(payload: PurchaseOrderInput, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchase.manage"))):
    order = _make_order(db, payload, actor)
    audit(db, actor, "purchase_order_created", "purchase_order", "success", str(order.id))
    db.commit()
    db.refresh(order)
    return _view(order, _lines(db, [order.id])[order.id])


@router.put("/{order_id}", response_model=PurchaseOrderView)
def replace_order(order_id: UUID, payload: PurchaseOrderInput, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchase.manage"))):
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "purchase order not found")
    if order.status != "draft":
        raise HTTPException(409, "only draft orders can be edited")
    supplier, product_lines = _validate_lines(db, payload)
    order.supplier_id, order.supplier_name = supplier.id, supplier.name
    old_lines = db.scalars(select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)).all()
    for line in old_lines:
        db.delete(line)
    db.flush()
    total = Decimal("0")
    for line, product in product_lines:
        line_total = (line.quantity * line.unit_cost).quantize(Decimal("0.01"))
        db.add(PurchaseOrderLine(purchase_order_id=order.id, product_id=product.id, product_sku=product.sku, product_name=product.name, quantity=line.quantity, unit_cost=line.unit_cost, line_total=line_total))
        total += line_total
    order.total = total
    audit(db, actor, "purchase_order_updated", "purchase_order", "success", str(order.id))
    db.commit()
    db.refresh(order)
    return _view(order, _lines(db, [order.id])[order.id])


@router.post("/{order_id}/confirm", response_model=PurchaseOrderView)
def confirm_order(order_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchase.manage"))):
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "purchase order not found")
    if order.status != "draft":
        raise HTTPException(409, "only draft orders can be confirmed")
    order.status = "confirmed"
    audit(db, actor, "purchase_order_confirmed", "purchase_order", "success", str(order.id))
    db.commit()
    return _view(order, _lines(db, [order.id])[order.id])


@router.post("/{order_id}/cancel", response_model=PurchaseOrderView)
def cancel_order(order_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchase.manage"))):
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "purchase order not found")
    if order.status not in {"draft", "confirmed"}:
        raise HTTPException(409, "order cannot be canceled")
    order.status = "canceled"
    audit(db, actor, "purchase_order_canceled", "purchase_order", "success", str(order.id))
    db.commit()
    return _view(order, _lines(db, [order.id])[order.id])


@router.post("/{order_id}/receive", response_model=PurchaseOrderView)
def receive_order(order_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("purchase.receive"))):
    order = db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "purchase order not found")
    lines = _lines(db, [order.id])[order.id]
    if order.status == "received":
        return _view(order, lines)
    if order.status != "confirmed":
        raise HTTPException(409, "only confirmed orders can be received")
    products = {product.id: product for product in db.scalars(select(Product).where(Product.id.in_([line.product_id for line in lines])).order_by(Product.id).with_for_update()).all()}
    for line in lines:
        product = products.get(line.product_id)
        if product is None or not product.is_active:
            raise HTTPException(409, "product no longer exists")
        product.stock_current += line.quantity
        db.add(InventoryMovement(product_id=product.id, user_id=actor.id, quantity=line.quantity, direction="in", reason="purchase", description=f"Recepción {order.order_number}", purchase_order_line_id=line.id))
    order.status = "received"
    audit(db, actor, "purchase_order_received", "purchase_order", "success", str(order.id), metadata={"total": str(order.total), "line_count": len(lines)})
    db.commit()
    db.refresh(order)
    return _view(order, lines)
