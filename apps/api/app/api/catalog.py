from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import audit, require_permission
from app.db.session import get_db
from app.models.entities import Category, Product, Supplier, User
from app.schemas.catalog import (
    CategoryCreate, CategoryList, CategoryUpdate, CategoryView, ProductCreate,
    ProductList, ProductUpdate, ProductView, SupplierCreate, SupplierList,
    SupplierUpdate, SupplierView,
)

router = APIRouter(tags=["catalog"])


def _list_args(page: int, page_size: int, search: str | None, active: bool | None) -> tuple[int, int, str | None, bool | None]:
    return page, page_size, search.strip() if search else None, active


def _commit_or_conflict(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="resource already exists") from None


@router.get("/categories", response_model=CategoryList)
def list_categories(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = Query(None, max_length=100), active: bool | None = None, sort: str = Query("name", pattern="^(code|name|created_at)$"), direction: str = Query("asc", pattern="^(asc|desc)$"), db: Session = Depends(get_db), _actor: User = Depends(require_permission("product.read"))):
    page, page_size, search, active = _list_args(page, page_size, search, active)
    condition = []
    if search:
        value = f"%{search.lower()}%"
        condition.append(or_(func.lower(Category.code).like(value), func.lower(Category.name).like(value)))
    if active is not None:
        condition.append(Category.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(Category).where(*condition)) or 0
    columns = {"code": Category.code, "name": Category.name, "created_at": Category.created_at}
    ordering = desc(columns[sort]) if direction == "desc" else asc(columns[sort])
    items = db.scalars(select(Category).where(*condition).order_by(ordering, Category.id).offset((page - 1) * page_size).limit(page_size)).all()
    return CategoryList(items=items, page=page, page_size=page_size, total=total)


@router.get("/categories/{category_id}", response_model=CategoryView)
def get_category(category_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(require_permission("product.read"))):
    item = db.get(Category, category_id)
    if item is None:
        raise HTTPException(404, "category not found")
    return item


@router.post("/categories", response_model=CategoryView, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("category.manage"))):
    item = Category(code=payload.code.upper(), name=payload.name)
    db.add(item)
    _commit_or_conflict(db)
    audit(db, actor, "category_created", "category", "success", str(item.id))
    db.commit()
    return item


@router.patch("/categories/{category_id}", response_model=CategoryView)
def update_category(category_id: UUID, payload: CategoryUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("category.manage"))):
    item = db.get(Category, category_id)
    if item is None:
        raise HTTPException(404, "category not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value.upper() if key == "code" else value)
    _commit_or_conflict(db)
    audit(db, actor, "category_updated", "category", "success", str(item.id))
    db.commit()
    return item


def _set_category_active(category_id: UUID, active: bool, db: Session, actor: User):
    item = db.scalar(select(Category).where(Category.id == category_id).with_for_update())
    if item is None:
        raise HTTPException(404, "category not found")
    item.is_active = active
    audit(db, actor, "category_activated" if active else "category_deactivated", "category", "success", str(item.id))
    db.commit()
    return item


@router.post("/categories/{category_id}/activate", response_model=CategoryView)
def activate_category(category_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("category.manage"))):
    return _set_category_active(category_id, True, db, actor)


@router.post("/categories/{category_id}/deactivate", response_model=CategoryView)
def deactivate_category(category_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("category.manage"))):
    return _set_category_active(category_id, False, db, actor)


@router.get("/suppliers", response_model=SupplierList)
def list_suppliers(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = Query(None, max_length=100), active: bool | None = None, sort: str = Query("name", pattern="^(code|name|created_at)$"), direction: str = Query("asc", pattern="^(asc|desc)$"), db: Session = Depends(get_db), _actor: User = Depends(require_permission("product.read"))):
    page, page_size, search, active = _list_args(page, page_size, search, active)
    condition = []
    if search:
        value = f"%{search.lower()}%"
        condition.append(or_(func.lower(Supplier.code).like(value), func.lower(Supplier.name).like(value)))
    if active is not None:
        condition.append(Supplier.is_active.is_(active))
    total = db.scalar(select(func.count()).select_from(Supplier).where(*condition)) or 0
    columns = {"code": Supplier.code, "name": Supplier.name, "created_at": Supplier.created_at}
    ordering = desc(columns[sort]) if direction == "desc" else asc(columns[sort])
    items = db.scalars(select(Supplier).where(*condition).order_by(ordering, Supplier.id).offset((page - 1) * page_size).limit(page_size)).all()
    return SupplierList(items=items, page=page, page_size=page_size, total=total)


@router.get("/suppliers/{supplier_id}", response_model=SupplierView)
def get_supplier(supplier_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(require_permission("product.read"))):
    item = db.get(Supplier, supplier_id)
    if item is None:
        raise HTTPException(404, "supplier not found")
    return item


@router.post("/suppliers", response_model=SupplierView, status_code=201)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("supplier.manage"))):
    item = Supplier(code=payload.code.upper(), name=payload.name)
    db.add(item)
    _commit_or_conflict(db)
    audit(db, actor, "supplier_created", "supplier", "success", str(item.id))
    db.commit()
    return item


@router.patch("/suppliers/{supplier_id}", response_model=SupplierView)
def update_supplier(supplier_id: UUID, payload: SupplierUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("supplier.manage"))):
    item = db.get(Supplier, supplier_id)
    if item is None:
        raise HTTPException(404, "supplier not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value.upper() if key == "code" else value)
    _commit_or_conflict(db)
    audit(db, actor, "supplier_updated", "supplier", "success", str(item.id))
    db.commit()
    return item


def _set_supplier_active(supplier_id: UUID, active: bool, db: Session, actor: User):
    item = db.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update())
    if item is None:
        raise HTTPException(404, "supplier not found")
    item.is_active = active
    audit(db, actor, "supplier_activated" if active else "supplier_deactivated", "supplier", "success", str(item.id))
    db.commit()
    return item


@router.post("/suppliers/{supplier_id}/activate", response_model=SupplierView)
def activate_supplier(supplier_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("supplier.manage"))):
    return _set_supplier_active(supplier_id, True, db, actor)


@router.post("/suppliers/{supplier_id}/deactivate", response_model=SupplierView)
def deactivate_supplier(supplier_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("supplier.manage"))):
    return _set_supplier_active(supplier_id, False, db, actor)


def _product_condition(search, active, category_id, supplier_id):
    condition = []
    if search:
        value = f"%{search.strip().lower()}%"
        condition.append(or_(func.lower(Product.sku).like(value), func.lower(Product.name).like(value)))
    if active is not None:
        condition.append(Product.is_active.is_(active))
    if category_id:
        condition.append(Product.category_id == category_id)
    if supplier_id:
        condition.append(Product.supplier_id == supplier_id)
    return condition


@router.get("/products", response_model=ProductList)
def list_products(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = Query(None, max_length=100), active: bool | None = None, category_id: UUID | None = None, supplier_id: UUID | None = None, sort: str = Query("name", pattern="^(sku|name|stock_current|created_at)$"), direction: str = Query("asc", pattern="^(asc|desc)$"), db: Session = Depends(get_db), _actor: User = Depends(require_permission("product.read"))):
    condition = _product_condition(search, active, category_id, supplier_id)
    total = db.scalar(select(func.count()).select_from(Product).where(*condition)) or 0
    columns = {"sku": Product.sku, "name": Product.name, "stock_current": Product.stock_current, "created_at": Product.created_at}
    ordering = desc(columns[sort]) if direction == "desc" else asc(columns[sort])
    items = db.scalars(select(Product).where(*condition).order_by(ordering, Product.id).offset((page - 1) * page_size).limit(page_size)).all()
    return ProductList(items=items, page=page, page_size=page_size, total=total)


@router.get("/products/{product_id}", response_model=ProductView)
def get_product(product_id: UUID, db: Session = Depends(get_db), _actor: User = Depends(require_permission("product.read"))):
    item = db.get(Product, product_id)
    if item is None:
        raise HTTPException(404, "product not found")
    return item


def _check_refs(db: Session, category_id: UUID, supplier_id: UUID | None):
    category = db.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(400, "active category required")
    if supplier_id is not None:
        supplier = db.get(Supplier, supplier_id)
        if supplier is None or not supplier.is_active:
            raise HTTPException(400, "active supplier required")


@router.post("/products", response_model=ProductView, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), actor: User = Depends(require_permission("product.create"))):
    _check_refs(db, payload.category_id, payload.supplier_id)
    item = Product(**payload.model_dump(), stock_current=0)
    item.sku = item.sku.upper()
    db.add(item)
    _commit_or_conflict(db)
    audit(db, actor, "product_created", "product", "success", str(item.id))
    db.commit()
    return item


@router.patch("/products/{product_id}", response_model=ProductView)
def update_product(product_id: UUID, payload: ProductUpdate, db: Session = Depends(get_db), actor: User = Depends(require_permission("product.update"))):
    item = db.get(Product, product_id)
    if item is None:
        raise HTTPException(404, "product not found")
    values = payload.model_dump(exclude_unset=True)
    _check_refs(db, values.get("category_id", item.category_id), values.get("supplier_id", item.supplier_id))
    for key, value in values.items():
        setattr(item, key, value.upper() if key == "sku" else value)
    _commit_or_conflict(db)
    audit(db, actor, "product_updated", "product", "success", str(item.id))
    db.commit()
    return item


def _set_product_active(product_id: UUID, active: bool, db: Session, actor: User):
    item = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if item is None:
        raise HTTPException(404, "product not found")
    item.is_active = active
    audit(db, actor, "product_activated" if active else "product_deactivated", "product", "success", str(item.id))
    db.commit()
    return item


@router.post("/products/{product_id}/activate", response_model=ProductView)
def activate_product(product_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("product.deactivate"))):
    return _set_product_active(product_id, True, db, actor)


@router.post("/products/{product_id}/deactivate", response_model=ProductView)
def deactivate_product(product_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_permission("product.deactivate"))):
    return _set_product_active(product_id, False, db, actor)
