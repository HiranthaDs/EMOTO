from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import time
import calendar
import hashlib
from html import escape
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession, selectinload

from .config import settings
from .database import engine, get_db
from .models import *
from .schemas import *
from .security import audit, current_user, hash_password, new_session, require, session_key, verify_password

router = APIRouter(prefix="/api/v1")
SAFE_UPLOADS = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "text/csv": ".csv"}
LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)


def data(model: Any, *, hide: set[str] | None = None) -> dict:
    hidden = hide or set()
    return {column.name: getattr(model, column.name) for column in model.__table__.columns if column.name not in hidden}


def page(db: DBSession, model, search: str | None, search_fields: list, page_no: int, size: int, filters=()):
    query = select(model).where(*filters)
    if search:
        query = query.where(or_(*[field.ilike(f"%{search}%") for field in search_fields]))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(model.id.desc()).offset((page_no - 1) * size).limit(size)).all()
    return {"items": [data(row) for row in rows], "total": total, "page": page_no, "page_size": size}


def sequence(db: DBSession, key: str, prefix: str) -> str:
    seq = db.get(DocumentSequence, key)
    if not seq:
        seq = DocumentSequence(key=key, value=0)
        db.add(seq)
        db.flush()
    seq.value += 1
    return f"{prefix}-{datetime.now().year}-{seq.value:05d}"


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


def quotation_total(quotation: Quotation) -> int:
    return max(0, sum(item.quantity * item.unit_price_cents for item in quotation.items) - quotation.discount_cents + quotation.additional_charges_cents)


def inventory_part_data(part: Part) -> dict:
    result = data(part)
    result["available_qty"] = part.physical_qty - part.reserved_qty
    result["stock_value_cents"] = part.physical_qty * part.purchase_cost_cents
    target = part.maximum_stock if part.maximum_stock is not None else part.reorder_level + part.reorder_quantity
    result["suggested_reorder_qty"] = max(0, target - result["available_qty"]) if result["available_qty"] <= part.reorder_level else 0
    return result


def apply_inventory_movement(
    db: DBSession,
    user: User,
    part: Part,
    kind: str,
    quantity: int | None,
    *,
    counted_quantity: int | None = None,
    movement_date: date | None = None,
    supplier_id: int | None = None,
    unit_cost_cents: int | None = None,
    overhead_cost_cents: int = 0,
    document_reference: str | None = None,
    batch_number: str | None = None,
    location: str | None = None,
    reference_type: str | None = None,
    reference_id: int | None = None,
    notes: str | None = None,
    consume_reserved: bool = False,
) -> InventoryMovement:
    physical_before, reserved_before = part.physical_qty, part.reserved_qty
    average_before = part.purchase_cost_cents
    physical_delta = reserved_delta = 0
    qty = quantity or 0

    if supplier_id and not db.get(Supplier, supplier_id):
        raise HTTPException(404, "Supplier not found")
    if kind in {"receive", "adjust_add", "return"}:
        physical_delta = qty
    elif kind in {"issue", "adjust_remove", "supplier_return"}:
        physical_delta = -qty
        required_reserved = reserved_before - qty if consume_reserved else reserved_before
        if physical_before + physical_delta < required_reserved:
            raise HTTPException(409, "Movement would reduce physical stock below reserved stock")
        if consume_reserved:
            if reserved_before < qty: raise HTTPException(409, "Reserved stock is unavailable")
            reserved_delta = -qty
    elif kind == "reserve":
        if physical_before - reserved_before < qty: raise HTTPException(409, "Insufficient available stock")
        reserved_delta = qty
    elif kind == "release":
        if reserved_before < qty: raise HTTPException(409, "Cannot release more than reserved")
        reserved_delta = -qty
    elif kind == "stocktake":
        if counted_quantity is None: raise HTTPException(422, "Counted quantity is required")
        if counted_quantity < reserved_before: raise HTTPException(409, "Counted stock cannot be lower than active reservations")
        physical_delta = counted_quantity - physical_before
        qty = abs(physical_delta)
    else:
        raise HTTPException(422, "Unsupported movement type")

    movement_cost = average_before if unit_cost_cents is None else unit_cost_cents
    landed_unit_cost = round((qty * movement_cost + overhead_cost_cents) / qty) if qty else movement_cost
    physical_after = physical_before + physical_delta
    reserved_after = reserved_before + reserved_delta
    if physical_after < 0 or reserved_after < 0 or physical_after < reserved_after:
        raise HTTPException(409, "Invalid stock balance")

    if kind == "receive":
        if unit_cost_cents is None: raise HTTPException(422, "Unit purchase cost is required when receiving stock")
        incoming_value = qty * unit_cost_cents + overhead_cost_cents
        part.purchase_cost_cents = round((physical_before * average_before + incoming_value) / physical_after) if physical_after else unit_cost_cents
        part.last_purchase_cost_cents = unit_cost_cents
        part.last_received_at = datetime.now(timezone.utc)
        if supplier_id and not part.default_supplier_id: part.default_supplier_id = supplier_id

    part.physical_qty = physical_after
    part.reserved_qty = reserved_after
    if location:
        part.location = location
    movement = InventoryMovement(
        number=sequence(db, "inventory_movement", "MOV"), part_id=part.id, movement_type=kind,
        quantity=qty, quantity_delta=physical_delta, reserved_delta=reserved_delta,
        quantity_before=physical_before, quantity_after=physical_after,
        reserved_before=reserved_before, reserved_after=reserved_after,
        unit_cost_cents=movement_cost, overhead_cost_cents=overhead_cost_cents, landed_unit_cost_cents=landed_unit_cost,
        total_cost_cents=qty * movement_cost + overhead_cost_cents,
        stock_value_before_cents=physical_before * average_before,
        stock_value_after_cents=physical_after * part.purchase_cost_cents,
        supplier_id=supplier_id, movement_date=movement_date or date.today(),
        document_reference=document_reference, batch_number=batch_number,
        location=location or part.location, reference_type=reference_type, reference_id=reference_id,
        notes=notes, created_by=user.id,
    )
    db.add(movement)
    return movement


def customer_document(db: DBSession, kind: str, document_id: int) -> dict:
    if kind == "quotation":
        document = db.scalar(select(Quotation).options(selectinload(Quotation.items)).where(Quotation.id == document_id))
        if not document: raise HTTPException(404, "Quotation not found")
        customer = db.get(Customer, document.customer_id)
        vehicle = db.get(Vehicle, document.vehicle_id) if document.vehicle_id else None
        return {"type": kind, "number": document.number, "status": document.status, "date": document.quote_date, "expiry_date": document.expiry_date, "customer": {"name": customer.full_name, "business_name": customer.business_name, "phone": customer.phone, "address": customer.billing_address or customer.address}, "vehicle": data(vehicle) if vehicle else None, "items": [{"description": item.description, "quantity": item.quantity, "unit_price_cents": item.unit_price_cents, "warranty": item.warranty, "amount_cents": item.quantity * item.unit_price_cents} for item in document.items], "discount_cents": document.discount_cents, "additional_charges_cents": document.additional_charges_cents, "total_cents": quotation_total(document), "notes": document.notes}
    if kind == "invoice":
        document = db.scalar(select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == document_id))
        if not document: raise HTTPException(404, "Invoice not found")
        customer = db.get(Customer, document.customer_id)
        order = db.get(SalesOrder, document.order_id)
        vehicle = db.get(Vehicle, order.vehicle_id) if order and order.vehicle_id else None
        return {"type": kind, "number": document.number, "status": document.status, "date": document.issue_date, "customer": {"name": customer.full_name, "business_name": customer.business_name, "phone": customer.phone, "address": customer.billing_address or customer.address}, "vehicle": data(vehicle) if vehicle else None, "items": [{"description": item.description, "quantity": item.quantity, "unit_price_cents": item.unit_price_cents, "amount_cents": item.quantity * item.unit_price_cents} for item in document.items], "total_cents": document.total_cents, "paid_cents": document.paid_cents, "balance_cents": document.total_cents - document.paid_cents}
    raise HTTPException(422, "Unsupported document type")


@router.get("/auth/setup-status")
def setup_status(db: DBSession = Depends(get_db)):
    return {"needs_setup": (db.scalar(select(func.count(User.id))) or 0) == 0}


@router.post("/auth/bootstrap", status_code=201)
def bootstrap(payload: BootstrapIn, request: Request, response: Response, db: DBSession = Depends(get_db)):
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "Setup has already been completed")
    if not settings.bootstrap_token or not secrets.compare_digest(payload.token, settings.bootstrap_token):
        raise HTTPException(403, "Invalid bootstrap token")
    user = User(email=payload.email.lower(), full_name=payload.full_name, password_hash=hash_password(payload.password), role="Super Admin")
    db.add(user)
    db.flush()
    audit(db, user, "system.bootstrap", "user", user.id, ip=request.client.host if request.client else None)
    db.commit()
    session = new_session(db, user)
    response.set_cookie("emoto_session", session.raw_id, httponly=True, secure=settings.production, samesite="lax", max_age=settings.session_hours * 3600, path="/")
    return {"user": data(user, hide={"password_hash"}), "csrf_token": session.csrf_token}


@router.post("/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db: DBSession = Depends(get_db)):
    key = f"{request.client.host if request.client else 'unknown'}:{payload.email.lower()}"
    now = time.monotonic()
    while LOGIN_ATTEMPTS[key] and now - LOGIN_ATTEMPTS[key][0] > 900:
        LOGIN_ATTEMPTS[key].popleft()
    if len(LOGIN_ATTEMPTS[key]) >= 5:
        raise HTTPException(429, "Too many login attempts. Try again later.")
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active:
        LOGIN_ATTEMPTS[key].append(now)
        audit(db, user, "auth.login_failed", details=payload.email, ip=request.client.host if request.client else None)
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    LOGIN_ATTEMPTS.pop(key, None)
    session = new_session(db, user)
    audit(db, user, "auth.login", ip=request.client.host if request.client else None)
    db.commit()
    response.set_cookie("emoto_session", session.raw_id, httponly=True, secure=settings.production, samesite="lax", max_age=settings.session_hours * 3600, path="/")
    return {"user": data(user, hide={"password_hash"}), "csrf_token": session.csrf_token}


@router.post("/auth/logout", status_code=204)
def logout(response: Response, request: Request, user: User = Depends(require("dashboard:view")), db: DBSession = Depends(get_db)):
    raw = request.cookies.get("emoto_session")
    session = db.get(Session, session_key(raw)) if raw else None
    if session:
        db.delete(session)
    audit(db, user, "auth.logout")
    db.commit()
    response.delete_cookie("emoto_session", path="/")


@router.get("/auth/me")
def me(user: User = Depends(current_user), request: Request = None, db: DBSession = Depends(get_db)):
    raw = request.cookies.get("emoto_session", "")
    session = db.get(Session, session_key(raw))
    return {"user": data(user, hide={"password_hash"}), "csrf_token": session.csrf_token}


@router.get("/dashboard")
def dashboard(user: User = Depends(require("dashboard:view")), db: DBSession = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    sales_today = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(Invoice.issue_date == today)) or 0
    sales_month = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(Invoice.issue_date >= month_start)) or 0
    outstanding = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents - Invoice.paid_cents), 0)).where(Invoice.status != "Paid")) or 0
    low_stock = db.scalar(select(func.count(Part.id)).where(Part.physical_qty - Part.reserved_qty <= Part.reorder_level, Part.status == "Active")) or 0
    stock_value = db.scalar(select(func.coalesce(func.sum(Part.physical_qty * Part.purchase_cost_cents), 0))) or 0
    kpis = {
        "sales_today": sales_today, "sales_month": sales_month, "outstanding": outstanding,
        "pending_quotations": db.scalar(select(func.count(Quotation.id)).where(Quotation.status.in_(["Draft", "Pending Approval", "Approved", "Sent"]))) or 0,
        "open_rfqs": db.scalar(select(func.count(RFQ.id)).where(~RFQ.status.in_(["Closed", "Cancelled"]))) or 0,
        "open_orders": db.scalar(select(func.count(SalesOrder.id)).where(~SalesOrder.status.in_(["Fulfilled", "Cancelled"]))) or 0,
        "low_stock": low_stock, "stock_value": stock_value,
        "active_warranties": db.scalar(select(func.count(Warranty.id)).where(Warranty.status == "Active")) or 0,
        "warranty_claims": db.scalar(select(func.count(WarrantyClaim.id)).where(WarrantyClaim.status != "Resolved")) or 0,
    }
    if user.role not in {"Super Admin", "Accounts", "Purchasing"}:
        for field in ("stock_value",): kpis[field] = None
    recent_invoices = db.scalars(select(Invoice).order_by(Invoice.id.desc()).limit(5)).all()
    movements = db.scalars(select(InventoryMovement).order_by(InventoryMovement.id.desc()).limit(6)).all()
    trend_start = today - timedelta(days=29)
    sales_rows = db.execute(select(Invoice.issue_date, func.sum(Invoice.total_cents)).where(Invoice.issue_date >= trend_start).group_by(Invoice.issue_date)).all()
    sales_map = {row[0]: row[1] for row in sales_rows}
    sales_trend = [{"date": (trend_start + timedelta(days=offset)).isoformat(), "sales_cents": sales_map.get(trend_start + timedelta(days=offset), 0)} for offset in range(30)]
    return {"kpis": kpis, "sales_trend": sales_trend, "recent_invoices": [data(x) for x in recent_invoices], "recent_movements": [data(x) for x in movements]}


@router.get("/search")
def global_search(q: str = Query(min_length=2, max_length=80), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    term = f"%{q}%"
    results = []
    specs = [(Customer, "customer", Customer.full_name, Customer.code), (Supplier, "supplier", Supplier.company_name, Supplier.code), (Part, "part", Part.name, Part.sku), (Quotation, "quotation", Quotation.number, Quotation.status), (SalesOrder, "order", SalesOrder.number, SalesOrder.status), (Invoice, "invoice", Invoice.number, Invoice.status)]
    for model, kind, label_col, meta_col in specs:
        rows = db.scalars(select(model).where(or_(label_col.ilike(term), meta_col.ilike(term))).limit(5)).all()
        results.extend({"type": kind, "id": row.id, "label": getattr(row, label_col.key), "meta": getattr(row, meta_col.key)} for row in rows)
    vehicles = db.scalars(select(Vehicle).where(or_(Vehicle.registration_number.ilike(term), Vehicle.vin.ilike(term), Vehicle.model.ilike(term))).limit(5)).all()
    for vehicle in vehicles:
        customer = db.get(Customer, vehicle.customer_id)
        results.append({"type": "customer", "id": customer.id, "label": f"{vehicle.registration_number or vehicle.vin or 'BMW'} · {customer.full_name}", "meta": f"BMW {vehicle.model}"})
    return results[:20]


@router.get("/suppliers")
def suppliers(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("suppliers:manage")), db: DBSession = Depends(get_db)):
    return page(db, Supplier, q, [Supplier.company_name, Supplier.code, Supplier.email], page_no, size)


@router.get("/suppliers/{supplier_id}")
def supplier_detail(supplier_id: int, user: User = Depends(require("suppliers:manage")), db: DBSession = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier: raise HTTPException(404, "Supplier not found")
    result = data(supplier)
    result["allocated_quotation_items"] = db.scalar(select(func.count()).select_from(QuotationItem).where(QuotationItem.supplier_id == supplier_id)) or 0
    result["allocated_order_items"] = db.scalar(select(func.count()).select_from(SalesOrderItem).where(SalesOrderItem.supplier_id == supplier_id)) or 0
    return result


@router.post("/suppliers", status_code=201)
def supplier_create(payload: SupplierIn, user: User = Depends(require("suppliers:manage")), db: DBSession = Depends(get_db)):
    supplier = Supplier(code=sequence(db, "supplier", "SUP"), **payload.model_dump())
    db.add(supplier); db.flush(); audit(db, user, "supplier.create", "supplier", supplier.id); db.commit()
    return data(supplier)


@router.put("/suppliers/{supplier_id}")
def supplier_update(supplier_id: int, payload: SupplierIn, user: User = Depends(require("suppliers:manage")), db: DBSession = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if not supplier: raise HTTPException(404, "Supplier not found")
    for key, value in payload.model_dump().items(): setattr(supplier, key, value)
    audit(db, user, "supplier.update", "supplier", supplier.id); db.commit()
    return data(supplier)


@router.get("/customers")
def customers(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("customers:view")), db: DBSession = Depends(get_db)):
    query = select(Customer).outerjoin(Vehicle).distinct()
    if q:
        term = f"%{q}%"
        query = query.where(or_(Customer.full_name.ilike(term), Customer.code.ilike(term), Customer.phone.ilike(term), Customer.email.ilike(term), Customer.business_name.ilike(term), Vehicle.registration_number.ilike(term), Vehicle.vin.ilike(term)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(Customer.id.desc()).offset((page_no - 1) * size).limit(size)).all()
    return {"items": [data(row) for row in rows], "total": total, "page": page_no, "page_size": size}


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: int, user: User = Depends(require("customers:view")), db: DBSession = Depends(get_db)):
    customer = db.scalar(select(Customer).options(selectinload(Customer.vehicles)).where(Customer.id == customer_id))
    if not customer: raise HTTPException(404, "Customer not found")
    result = data(customer); result["vehicles"] = [data(x) for x in customer.vehicles]
    quotations = db.scalars(select(Quotation).options(selectinload(Quotation.items)).where(Quotation.customer_id == customer_id).order_by(Quotation.id.desc()).limit(20)).all()
    result["quotations"] = [{**data(x), "total_cents": quotation_total(x), "items": [{**data(item), "supplier": data(db.get(Supplier, item.supplier_id), hide={"bank_details"}) if item.supplier_id else None} for item in x.items]} for x in quotations]
    result["invoices"] = [data(x) for x in db.scalars(select(Invoice).where(Invoice.customer_id == customer_id).order_by(Invoice.id.desc()).limit(20))]
    services = db.scalars(select(ServiceRecord).options(selectinload(ServiceRecord.items)).where(ServiceRecord.customer_id == customer_id).order_by(ServiceRecord.service_date.desc(), ServiceRecord.id.desc()).limit(20)).all()
    result["service_history"] = [{**data(record), "vehicle": data(db.get(Vehicle, record.vehicle_id)), "items": [data(item) for item in record.items]} for record in services]
    result["lifetime_sales_cents"] = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(Invoice.customer_id == customer_id)) or 0
    result["outstanding_cents"] = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents - Invoice.paid_cents), 0)).where(Invoice.customer_id == customer_id)) or 0
    return result


@router.post("/customers", status_code=201)
def customer_create(payload: CustomerIn, user: User = Depends(require("customers:manage")), db: DBSession = Depends(get_db)):
    customer = Customer(code=sequence(db, "customer", "CUS"), **payload.model_dump())
    db.add(customer); db.flush(); audit(db, user, "customer.create", "customer", customer.id); db.commit()
    return data(customer)


@router.post("/customer-profiles", status_code=201)
def customer_with_vehicle_create(payload: CustomerVehicleIn, user: User = Depends(require("customers:manage")), db: DBSession = Depends(get_db)):
    registration = payload.vehicle.registration_number.strip().upper()
    if db.scalar(select(Vehicle).where(func.upper(Vehicle.registration_number) == registration)):
        raise HTTPException(409, "This vehicle registration is already linked to a customer")
    customer = Customer(code=sequence(db, "customer", "CUS"), **payload.customer.model_dump())
    db.add(customer); db.flush()
    vehicle = Vehicle(customer_id=customer.id, **payload.vehicle.model_dump(exclude={"registration_number"}), registration_number=registration)
    db.add(vehicle); db.flush(); audit(db, user, "customer_vehicle.create", "customer", customer.id, f"vehicle={registration}"); db.commit()
    return {"customer": data(customer), "vehicle": data(vehicle)}


@router.put("/customers/{customer_id}")
def customer_update(customer_id: int, payload: CustomerIn, user: User = Depends(require("customers:manage")), db: DBSession = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer: raise HTTPException(404, "Customer not found")
    for key, value in payload.model_dump().items(): setattr(customer, key, value)
    audit(db, user, "customer.update", "customer", customer.id); db.commit()
    return data(customer)


@router.get("/vehicles")
def vehicles(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("vehicles:manage")), db: DBSession = Depends(get_db)):
    return page(db, Vehicle, q, [Vehicle.brand, Vehicle.model, Vehicle.registration_number, Vehicle.vin], page_no, size)


@router.post("/vehicles", status_code=201)
def vehicle_create(payload: VehicleIn, user: User = Depends(require("vehicles:manage")), db: DBSession = Depends(get_db)):
    if not db.get(Customer, payload.customer_id): raise HTTPException(404, "Customer not found")
    values = payload.model_dump()
    if values["registration_number"]:
        values["registration_number"] = values["registration_number"].strip().upper()
        if db.scalar(select(Vehicle).where(func.upper(Vehicle.registration_number) == values["registration_number"])):
            raise HTTPException(409, "This vehicle registration is already linked to a customer")
    vehicle = Vehicle(**values); db.add(vehicle); db.flush(); audit(db, user, "vehicle.create", "vehicle", vehicle.id); db.commit()
    return data(vehicle)


@router.get("/parts")
def parts(q: str | None = None, low_stock: bool = False, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("parts:view")), db: DBSession = Depends(get_db)):
    filters = [Part.physical_qty - Part.reserved_qty <= Part.reorder_level] if low_stock else []
    result = page(db, Part, q, [Part.sku, Part.name, Part.manufacturer_reference, Part.oem_reference, Part.fitment_notes], page_no, size, filters)
    for item in result["items"]:
        item["available_qty"] = item["physical_qty"] - item["reserved_qty"]
        item["stock_value_cents"] = item["physical_qty"] * item["purchase_cost_cents"]
        target = item["maximum_stock"] if item["maximum_stock"] is not None else item["reorder_level"] + item["reorder_quantity"]
        item["suggested_reorder_qty"] = max(0, target - item["available_qty"]) if item["available_qty"] <= item["reorder_level"] else 0
    if user.role not in {"Super Admin", "Purchasing", "Inventory", "Accounts"}:
        for item in result["items"]:
            item.pop("purchase_cost_cents", None); item.pop("last_purchase_cost_cents", None); item.pop("stock_value_cents", None)
    return result


@router.post("/parts", status_code=201)
def part_create(payload: PartIn, user: User = Depends(require("parts:manage")), db: DBSession = Depends(get_db)):
    if payload.default_supplier_id and not db.get(Supplier, payload.default_supplier_id): raise HTTPException(404, "Default supplier not found")
    values = payload.model_dump()
    if values["last_purchase_cost_cents"] == 0: values["last_purchase_cost_cents"] = values["purchase_cost_cents"]
    part = Part(**values); db.add(part)
    try: db.flush()
    except IntegrityError: raise HTTPException(409, "SKU already exists")
    audit(db, user, "part.create", "part", part.id); db.commit()
    return data(part)


@router.get("/services")
def services(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(100, le=100), user: User = Depends(require("services:view")), db: DBSession = Depends(get_db)):
    return page(db, Service, q, [Service.code, Service.name, Service.category, Service.description], page_no, size)


@router.post("/services", status_code=201)
def service_create(payload: ServiceIn, user: User = Depends(require("services:manage")), db: DBSession = Depends(get_db)):
    service = Service(code=sequence(db, "service", "SVC"), **payload.model_dump())
    db.add(service); db.flush(); audit(db, user, "service.create", "service", service.id); db.commit()
    return data(service)


@router.get("/service-records")
def service_records(customer_id: int | None = None, vehicle_id: int | None = None, user: User = Depends(require("services:view")), db: DBSession = Depends(get_db)):
    filters = []
    if customer_id: filters.append(ServiceRecord.customer_id == customer_id)
    if vehicle_id: filters.append(ServiceRecord.vehicle_id == vehicle_id)
    records = db.scalars(select(ServiceRecord).options(selectinload(ServiceRecord.items)).where(*filters).order_by(ServiceRecord.service_date.desc(), ServiceRecord.id.desc()).limit(100)).all()
    return [{**data(record), "items": [data(item) for item in record.items]} for record in records]


@router.get("/pos/customer-search")
def pos_customer_search(q: str = Query("", max_length=80), user: User = Depends(require("pos:manage")), db: DBSession = Depends(get_db)):
    query = select(Customer).options(selectinload(Customer.vehicles)).outerjoin(Vehicle).distinct()
    term = q.strip()
    if term:
        match = f"%{term}%"
        query = query.where(or_(
            Customer.full_name.ilike(match), Customer.code.ilike(match), Customer.phone.ilike(match),
            Customer.whatsapp.ilike(match), Customer.email.ilike(match),
            Vehicle.registration_number.ilike(match), Vehicle.vin.ilike(match),
            Vehicle.model.ilike(match), Vehicle.chassis_code.ilike(match),
        ))
    customers = db.scalars(query.order_by(Customer.updated_at.desc()).limit(12)).unique().all()
    return {"items": [{**data(customer), "vehicles": [data(vehicle) for vehicle in customer.vehicles]} for customer in customers]}


@router.post("/pos/checkout", status_code=201)
def pos_checkout(payload: POSCheckoutIn, user: User = Depends(require("pos:manage")), db: DBSession = Depends(get_db)):
    customer = db.get(Customer, payload.customer_id)
    if not customer: raise HTTPException(404, "Customer not found")
    vehicle = db.get(Vehicle, payload.vehicle_id) if payload.vehicle_id else None
    if payload.vehicle_id and (not vehicle or vehicle.customer_id != customer.id): raise HTTPException(422, "Vehicle does not belong to the selected customer")
    if any(line.item_type in {"service", "manual"} for line in payload.lines) and not vehicle: raise HTTPException(422, "Select a customer vehicle for workshop services")
    subtotal = sum(line.quantity * line.unit_price_cents for line in payload.lines)
    total = max(0, subtotal + payload.service_fee_cents - payload.discount_cents)
    if payload.payment_amount_cents > total: raise HTTPException(409, "Payment exceeds invoice total")
    order = SalesOrder(number=sequence(db, "order", "SO"), customer_id=customer.id, vehicle_id=vehicle.id if vehicle else None, status="Fulfilled", discount_cents=payload.discount_cents, additional_charges_cents=payload.service_fee_cents, created_by=user.id)
    db.add(order); db.flush()
    order_lines: list[tuple[POSLineIn, SalesOrderItem]] = []
    for line in payload.lines:
        part = db.scalar(select(Part).where(Part.id == line.part_id).with_for_update()) if line.part_id else None
        service = db.get(Service, line.service_id) if line.service_id else None
        if line.item_type == "part" and not part: raise HTTPException(404, f"Part not found: {line.description}")
        if line.item_type == "service" and not service: raise HTTPException(404, f"Service not found: {line.description}")
        if part:
            if part.physical_qty - part.reserved_qty < line.quantity: raise HTTPException(409, f"Insufficient available stock for {part.name}")
            apply_inventory_movement(db, user, part, "issue", line.quantity, reference_type="pos", reference_id=order.id, document_reference=order.number, notes=f"POS issue for {order.number}")
        order_item = SalesOrderItem(part_id=part.id if part else None, service_id=service.id if service else None, description=line.description, quantity=line.quantity, unit_price_cents=line.unit_price_cents, cost_cents=part.purchase_cost_cents if part else 0, fulfilled_qty=line.quantity)
        order.items.append(order_item); order_lines.append((line, order_item))
    db.flush()
    invoice = Invoice(number=sequence(db, "invoice", "INV"), order_id=order.id, customer_id=customer.id, total_cents=total, paid_cents=payload.payment_amount_cents, status="Paid" if payload.payment_amount_cents == total else "Partially Paid" if payload.payment_amount_cents else "Unpaid")
    invoice.items = [InvoiceItem(order_item_id=order_item.id, part_id=order_item.part_id, service_id=order_item.service_id, description=line.description, quantity=line.quantity, unit_price_cents=line.unit_price_cents) for line, order_item in order_lines]
    db.add(invoice); db.flush()
    if payload.payment_amount_cents:
        db.add(Payment(invoice_id=invoice.id, amount_cents=payload.payment_amount_cents, method=payload.payment_method, reference=payload.payment_reference, recorded_by=user.id))
    service_record = None
    if vehicle and (any(line.item_type in {"service", "manual"} for line in payload.lines) or payload.service_fee_cents or payload.notes):
        service_record = ServiceRecord(number=sequence(db, "service_record", "JOB"), customer_id=customer.id, vehicle_id=vehicle.id, invoice_id=invoice.id, service_date=payload.service_date, odometer_km=payload.odometer_km, technician=payload.technician, next_service_date=payload.next_service_date, next_service_km=payload.next_service_km, notes=payload.notes, created_by=user.id)
        service_record.items = [ServiceRecordItem(service_id=line.service_id, part_id=line.part_id, description=line.description, quantity=line.quantity, unit_price_cents=line.unit_price_cents) for line in payload.lines]
        if payload.service_fee_cents: service_record.items.append(ServiceRecordItem(description="Workshop service fee", quantity=1, unit_price_cents=payload.service_fee_cents))
        db.add(service_record)
        if payload.odometer_km is not None: vehicle.mileage_km = max(vehicle.mileage_km or 0, payload.odometer_km)
    audit(db, user, "pos.checkout", "invoice", invoice.id, f"order={order.number}; total_cents={total}"); db.commit()
    return {"invoice": data(invoice), "order": data(order), "service_record": data(service_record) if service_record else None, "balance_cents": total - payload.payment_amount_cents}


@router.post("/inventory/movements", status_code=201)
def inventory_move(payload: MovementIn, user: User = Depends(require("inventory:manage")), db: DBSession = Depends(get_db)):
    part = db.scalar(select(Part).where(Part.id == payload.part_id).with_for_update())
    if not part: raise HTTPException(404, "Part not found")
    movement = apply_inventory_movement(db, user, part, payload.movement_type, payload.quantity,
        counted_quantity=payload.counted_quantity, movement_date=payload.movement_date,
        supplier_id=payload.supplier_id, unit_cost_cents=payload.unit_cost_cents,
        overhead_cost_cents=payload.overhead_cost_cents,
        document_reference=payload.document_reference, batch_number=payload.batch_number,
        location=payload.location, notes=payload.notes)
    db.flush(); audit(db, user, f"inventory.{payload.movement_type}", "part", part.id, f"movement={movement.number}; delta={movement.quantity_delta}; value={movement.total_cost_cents}"); db.commit()
    return {"movement": data(movement), "part": inventory_part_data(part)}


@router.get("/inventory/movements")
def inventory_movements(page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("inventory:manage")), db: DBSession = Depends(get_db)):
    return page(db, InventoryMovement, None, [], page_no, size)


@router.get("/inventory/overview")
def inventory_overview(q: str | None = None, user: User = Depends(require("inventory:manage")), db: DBSession = Depends(get_db)):
    query = select(Part)
    if q:
        term = f"%{q}%"
        query = query.where(or_(Part.sku.ilike(term), Part.name.ilike(term), Part.oem_reference.ilike(term), Part.barcode.ilike(term), Part.location.ilike(term)))
    parts = db.scalars(query.order_by(Part.name).limit(250)).all()
    all_parts = db.scalars(select(Part)).all()
    movements = db.scalars(select(InventoryMovement).order_by(InventoryMovement.id.desc()).limit(50)).all()
    supplier_ids = {movement.supplier_id for movement in movements if movement.supplier_id}
    suppliers = {supplier.id: supplier.company_name for supplier in db.scalars(select(Supplier).where(Supplier.id.in_(supplier_ids))).all()} if supplier_ids else {}
    user_ids = {movement.created_by for movement in movements}
    users = {staff.id: staff.full_name for staff in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    part_names = {part.id: {"sku": part.sku, "name": part.name} for part in all_parts}
    movement_rows = []
    for movement in movements:
        movement_rows.append({**data(movement), "part": part_names.get(movement.part_id), "supplier_name": suppliers.get(movement.supplier_id), "created_by_name": users.get(movement.created_by)})
    return {
        "summary": {
            "total_skus": len(all_parts),
            "physical_units": sum(part.physical_qty for part in all_parts),
            "reserved_units": sum(part.reserved_qty for part in all_parts),
            "available_units": sum(part.physical_qty - part.reserved_qty for part in all_parts),
            "stock_value_cents": sum(part.physical_qty * part.purchase_cost_cents for part in all_parts),
            "retail_value_cents": sum(part.physical_qty * part.selling_price_cents for part in all_parts),
            "potential_margin_cents": sum(part.physical_qty * max(0, part.selling_price_cents - part.purchase_cost_cents) for part in all_parts),
            "low_stock_items": sum(1 for part in all_parts if part.physical_qty - part.reserved_qty <= part.reorder_level),
        },
        "items": [inventory_part_data(part) for part in parts],
        "movements": movement_rows,
    }


@router.get("/rfqs")
def rfqs(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("rfqs:manage")), db: DBSession = Depends(get_db)):
    return page(db, RFQ, q, [RFQ.number, RFQ.status], page_no, size)


@router.post("/rfqs", status_code=201)
def rfq_create(payload: RFQIn, user: User = Depends(require("rfqs:manage")), db: DBSession = Depends(get_db)):
    rfq = RFQ(number=sequence(db, "rfq", "RFQ"), customer_id=payload.customer_id, requested_delivery_date=payload.requested_delivery_date, notes=payload.notes, created_by=user.id)
    rfq.items = [RFQItem(**item.model_dump()) for item in payload.items]
    rfq.suppliers = [RFQSupplier(supplier_id=supplier_id) for supplier_id in set(payload.supplier_ids)]
    db.add(rfq); db.flush(); audit(db, user, "rfq.create", "rfq", rfq.id); db.commit()
    return data(rfq)


@router.get("/rfqs/{rfq_id}")
def rfq_detail(rfq_id: int, user: User = Depends(require("rfqs:manage")), db: DBSession = Depends(get_db)):
    rfq = db.scalar(select(RFQ).options(selectinload(RFQ.items), selectinload(RFQ.suppliers)).where(RFQ.id == rfq_id))
    if not rfq: raise HTTPException(404, "RFQ not found")
    result = data(rfq); result["items"] = [data(x) for x in rfq.items]; result["suppliers"] = [data(x) for x in rfq.suppliers]
    quotes = db.scalars(select(SupplierQuote).options(selectinload(SupplierQuote.items)).where(SupplierQuote.rfq_id == rfq_id)).all()
    result["quotes"] = [{**data(q), "items": [data(i) for i in q.items]} for q in quotes]
    return result


@router.post("/rfqs/{rfq_id}/quotes", status_code=201)
def supplier_quote_create(rfq_id: int, payload: SupplierQuoteIn, user: User = Depends(require("rfqs:manage")), db: DBSession = Depends(get_db)):
    rfq = db.get(RFQ, rfq_id)
    if not rfq: raise HTTPException(404, "RFQ not found")
    allowed = set(db.scalars(select(RFQItem.id).where(RFQItem.rfq_id == rfq_id)).all())
    if any(i.rfq_item_id not in allowed for i in payload.items): raise HTTPException(422, "Quote item does not belong to RFQ")
    quote = SupplierQuote(rfq_id=rfq_id, **payload.model_dump(exclude={"items"}))
    quote.items = [SupplierQuoteItem(**item.model_dump()) for item in payload.items]
    db.add(quote); rfq.status = "Partially Responded"; db.flush()
    linked = db.scalar(select(RFQSupplier).where(RFQSupplier.rfq_id == rfq_id, RFQSupplier.supplier_id == payload.supplier_id))
    if linked: linked.response_status = "Responded"
    audit(db, user, "supplier_quote.create", "supplier_quote", quote.id); db.commit()
    return data(quote)


@router.post("/rfqs/{rfq_id}/quotes/{quote_id}/select")
def supplier_quote_select(rfq_id: int, quote_id: int, user: User = Depends(require("rfqs:manage")), db: DBSession = Depends(get_db)):
    quote = db.scalar(select(SupplierQuote).where(SupplierQuote.id == quote_id, SupplierQuote.rfq_id == rfq_id))
    if not quote: raise HTTPException(404, "Quote not found")
    for other in db.scalars(select(SupplierQuote).where(SupplierQuote.rfq_id == rfq_id)): other.selected = False
    quote.selected = True; quote.approved_by = user.id; db.get(RFQ, rfq_id).status = "Approved"
    audit(db, user, "supplier_quote.select", "supplier_quote", quote.id); db.commit()
    return data(quote)


@router.get("/quotations")
def quotations(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("quotations:manage")), db: DBSession = Depends(get_db)):
    return page(db, Quotation, q, [Quotation.number, Quotation.status], page_no, size)


@router.post("/quotations", status_code=201)
def quotation_create(payload: QuotationIn, user: User = Depends(require("quotations:manage")), db: DBSession = Depends(get_db)):
    if not db.get(Customer, payload.customer_id): raise HTTPException(404, "Customer not found")
    if payload.vehicle_id:
        vehicle = db.get(Vehicle, payload.vehicle_id)
        if not vehicle or vehicle.customer_id != payload.customer_id: raise HTTPException(422, "Vehicle does not belong to the selected customer")
    quotation = Quotation(number=sequence(db, "quotation", "QUO"), customer_id=payload.customer_id, vehicle_id=payload.vehicle_id, expiry_date=payload.expiry_date, discount_cents=payload.discount_cents, additional_charges_cents=payload.additional_charges_cents, notes=payload.notes, created_by=user.id)
    quotation.items = []
    for line in payload.items:
        part = db.get(Part, line.part_id) if line.part_id else None
        service = db.get(Service, line.service_id) if line.service_id else None
        supplier = db.get(Supplier, line.supplier_id) if line.supplier_id else None
        if line.service_id and not service: raise HTTPException(404, "Service not found")
        if line.supplier_id and not supplier: raise HTTPException(404, "Allocated supplier not found")
        values = line.model_dump()
        if values["unit_cost_cents"] == 0 and part: values["unit_cost_cents"] = part.purchase_cost_cents
        if not values["supplier_reference"] and supplier: values["supplier_reference"] = supplier.supplier_reference
        quotation.items.append(QuotationItem(**values))
    db.add(quotation); db.flush(); audit(db, user, "quotation.create", "quotation", quotation.id); db.commit()
    result = data(quotation); result["total_cents"] = quotation_total(quotation)
    return result


@router.get("/quotations/{quotation_id}")
def quotation_detail(quotation_id: int, user: User = Depends(require("quotations:manage")), db: DBSession = Depends(get_db)):
    quotation = db.scalar(select(Quotation).options(selectinload(Quotation.items)).where(Quotation.id == quotation_id))
    if not quotation: raise HTTPException(404, "Quotation not found")
    result = data(quotation); result["total_cents"] = quotation_total(quotation)
    result["customer"] = data(db.get(Customer, quotation.customer_id))
    result["vehicle"] = data(db.get(Vehicle, quotation.vehicle_id)) if quotation.vehicle_id else None
    result["items"] = [{**data(item), "supplier": data(db.get(Supplier, item.supplier_id), hide={"bank_details"}) if item.supplier_id else None} for item in quotation.items]
    return result


@router.post("/quotations/{quotation_id}/approve")
def quotation_approve(quotation_id: int, user: User = Depends(require("quotations:manage")), db: DBSession = Depends(get_db)):
    quotation = db.get(Quotation, quotation_id)
    if not quotation: raise HTTPException(404, "Quotation not found")
    if quotation.status not in {"Draft", "Pending Approval"}: raise HTTPException(409, "Quotation cannot be approved from its current state")
    quotation.status = "Approved"; audit(db, user, "quotation.approve", "quotation", quotation.id); db.commit()
    return data(quotation)


@router.post("/quotations/{quotation_id}/convert", status_code=201)
def quotation_convert(quotation_id: int, user: User = Depends(require("orders:manage")), db: DBSession = Depends(get_db)):
    quotation = db.scalar(select(Quotation).options(selectinload(Quotation.items)).where(Quotation.id == quotation_id))
    if not quotation: raise HTTPException(404, "Quotation not found")
    existing = db.scalar(select(SalesOrder).where(SalesOrder.quotation_id == quotation_id))
    if existing: return data(existing)
    if quotation.status not in {"Approved", "Accepted", "Sent"}: raise HTTPException(409, "Approve the quotation before conversion")
    order = SalesOrder(number=sequence(db, "order", "SO"), quotation_id=quotation.id, customer_id=quotation.customer_id, vehicle_id=quotation.vehicle_id, status="Confirmed", discount_cents=quotation.discount_cents, additional_charges_cents=quotation.additional_charges_cents, created_by=user.id)
    db.add(order); db.flush()
    for item in quotation.items:
        part = db.get(Part, item.part_id) if item.part_id else None
        if part and part.physical_qty - part.reserved_qty >= item.quantity:
            apply_inventory_movement(db, user, part, "reserve", item.quantity, reference_type="order", reference_id=order.id, document_reference=order.number, notes=f"Reserved for {order.number}")
        order.items.append(SalesOrderItem(part_id=item.part_id, service_id=item.service_id, supplier_id=item.supplier_id, supplier_reference=item.supplier_reference, description=item.description, quantity=item.quantity, unit_price_cents=item.unit_price_cents, cost_cents=item.unit_cost_cents or (part.purchase_cost_cents if part else 0)))
    quotation.status = "Converted"; db.flush(); audit(db, user, "quotation.convert", "order", order.id); db.commit()
    return data(order)


@router.get("/orders")
def orders(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("orders:view")), db: DBSession = Depends(get_db)):
    return page(db, SalesOrder, q, [SalesOrder.number, SalesOrder.status], page_no, size)


@router.post("/orders/{order_id}/dispatch")
def dispatch_order(order_id: int, user: User = Depends(require("inventory:manage")), db: DBSession = Depends(get_db)):
    order = db.scalar(select(SalesOrder).options(selectinload(SalesOrder.items)).where(SalesOrder.id == order_id))
    if not order: raise HTTPException(404, "Order not found")
    if order.status in {"Fulfilled", "Cancelled"}: raise HTTPException(409, "Order cannot be dispatched")
    for item in order.items:
        if not item.part_id or item.fulfilled_qty >= item.quantity: continue
        qty = item.quantity - item.fulfilled_qty; part = db.get(Part, item.part_id)
        if not part or part.physical_qty < qty or part.reserved_qty < qty: raise HTTPException(409, f"Reserved stock unavailable for {item.description}")
        apply_inventory_movement(db, user, part, "issue", qty, reference_type="order", reference_id=order.id, document_reference=order.number, notes=f"Issued for {order.number}", consume_reserved=True)
        item.fulfilled_qty += qty
    order.status = "Fulfilled"; audit(db, user, "order.dispatch", "order", order.id); db.commit()
    return data(order)


@router.post("/orders/{order_id}/invoice", status_code=201)
def generate_invoice(order_id: int, user: User = Depends(require("invoices:manage")), db: DBSession = Depends(get_db)):
    existing = db.scalar(select(Invoice).where(Invoice.order_id == order_id))
    if existing: return data(existing)
    order = db.scalar(select(SalesOrder).options(selectinload(SalesOrder.items)).where(SalesOrder.id == order_id))
    if not order: raise HTTPException(404, "Order not found")
    if order.status == "Cancelled": raise HTTPException(409, "Cancelled orders cannot be invoiced")
    invoice_total = max(0, sum(x.quantity * x.unit_price_cents for x in order.items) - order.discount_cents + order.additional_charges_cents)
    invoice = Invoice(number=sequence(db, "invoice", "INV"), order_id=order.id, customer_id=order.customer_id, total_cents=invoice_total)
    invoice.items = [InvoiceItem(order_item_id=x.id, part_id=x.part_id, service_id=x.service_id, description=x.description, quantity=x.quantity, unit_price_cents=x.unit_price_cents) for x in order.items]
    db.add(invoice); db.flush(); audit(db, user, "invoice.create", "invoice", invoice.id); db.commit()
    return data(invoice)


@router.get("/invoices")
def invoices(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("invoices:view")), db: DBSession = Depends(get_db)):
    return page(db, Invoice, q, [Invoice.number, Invoice.status], page_no, size)


@router.get("/invoices/{invoice_id}")
def invoice_detail(invoice_id: int, user: User = Depends(require("invoices:view")), db: DBSession = Depends(get_db)):
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.items), selectinload(Invoice.payments)).where(Invoice.id == invoice_id))
    if not invoice: raise HTTPException(404, "Invoice not found")
    order = db.scalar(select(SalesOrder).options(selectinload(SalesOrder.items)).where(SalesOrder.id == invoice.order_id))
    result = data(invoice); result["customer"] = data(db.get(Customer, invoice.customer_id)); result["vehicle"] = data(db.get(Vehicle, order.vehicle_id)) if order and order.vehicle_id else None
    order_items = {item.id: item for item in order.items} if order else {}
    result["items"] = []
    for item in invoice.items:
        source = order_items.get(item.order_item_id)
        supplier = db.get(Supplier, source.supplier_id) if source and source.supplier_id else None
        result["items"].append({**data(item), "supplier": data(supplier, hide={"bank_details"}) if supplier else None, "supplier_reference": source.supplier_reference if source else None})
    result["payments"] = [data(payment) for payment in invoice.payments]
    result["balance_cents"] = invoice.total_cents - invoice.paid_cents
    return result


@router.post("/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: int, payload: PaymentIn, user: User = Depends(require("payments:manage")), db: DBSession = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice: raise HTTPException(404, "Invoice not found")
    if payload.amount_cents > invoice.total_cents - invoice.paid_cents: raise HTTPException(409, "Payment exceeds outstanding balance")
    payment = Payment(invoice_id=invoice.id, recorded_by=user.id, **payload.model_dump()); invoice.paid_cents += payload.amount_cents
    invoice.status = "Paid" if invoice.paid_cents == invoice.total_cents else "Partially Paid"
    db.add(payment); db.flush(); audit(db, user, "payment.create", "payment", payment.id); db.commit()
    return {"payment": data(payment), "invoice": data(invoice)}


def create_document_share(db: DBSession, kind: str, document_id: int, expires_days: int, user: User, request: Request) -> dict:
    customer_document(db, kind, document_id)
    raw_token = secrets.token_urlsafe(32)
    share = DocumentShare(document_type=kind, document_id=document_id, token_hash=hashlib.sha256(raw_token.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days), created_by=user.id)
    db.add(share); db.flush(); audit(db, user, "document.share", kind, document_id, f"expires_days={expires_days}"); db.commit()
    base_url = (settings.public_base_url or str(request.base_url)).rstrip("/")
    return {"url": f"{base_url}/share/{raw_token}", "expires_at": share.expires_at}


@router.post("/quotations/{quotation_id}/share", status_code=201)
def share_quotation(quotation_id: int, payload: ShareIn, request: Request, user: User = Depends(require("quotations:manage")), db: DBSession = Depends(get_db)):
    return create_document_share(db, "quotation", quotation_id, payload.expires_days, user, request)


@router.post("/invoices/{invoice_id}/share", status_code=201)
def share_invoice(invoice_id: int, payload: ShareIn, request: Request, user: User = Depends(require("invoices:manage")), db: DBSession = Depends(get_db)):
    return create_document_share(db, "invoice", invoice_id, payload.expires_days, user, request)


@router.get("/public/shares/{token}")
def public_document(token: str, db: DBSession = Depends(get_db)):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    share = db.scalar(select(DocumentShare).where(DocumentShare.token_hash == token_hash))
    if not share or share.revoked_at: raise HTTPException(404, "This document link is unavailable")
    expires = share.expires_at
    if expires and expires.tzinfo is None: expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= datetime.now(timezone.utc): raise HTTPException(410, "This document link has expired")
    share.last_viewed_at = datetime.now(timezone.utc); result = customer_document(db, share.document_type, share.document_id); db.commit()
    result["shared_until"] = share.expires_at
    return result


def verified_share_url(db: DBSession, request: Request, kind: str, document_id: int, token: str | None) -> str | None:
    if not token: return None
    share = db.scalar(select(DocumentShare).where(DocumentShare.token_hash == hashlib.sha256(token.encode()).hexdigest(), DocumentShare.document_type == kind, DocumentShare.document_id == document_id, DocumentShare.revoked_at.is_(None)))
    if not share: raise HTTPException(422, "The QR link is invalid for this document")
    expires = share.expires_at
    if expires and expires.tzinfo is None: expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires <= datetime.now(timezone.utc): raise HTTPException(410, "The QR link has expired")
    base_url = (settings.public_base_url or str(request.base_url)).rstrip("/")
    return f"{base_url}/share/{token}"


def document_pdf(document: dict, qr_url: str | None = None) -> bytes:
    stream = BytesIO(); pdf = SimpleDocTemplate(stream, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=15*mm, bottomMargin=15*mm, title=f"{document['number']} - EMOTO")
    styles = getSampleStyleSheet(); green = colors.HexColor("#249b68"); dark = colors.HexColor("#171717"); line = colors.HexColor("#dddddd")
    title = "INVOICE" if document["type"] == "invoice" else "QUOTATION"
    brand = Paragraph("<font size='18'><b>EMOTO</b></font><br/><font color='#249b68' size='8'>BMW SPARE PARTS</font>", styles["BodyText"])
    meta = Paragraph(f"<font size='16'><b>{title}</b></font><br/><font size='9' color='#666666'>{document['number']}<br/>{document['date']}</font>", styles["BodyText"])
    header = Table([[brand, meta]], colWidths=[115*mm, 62*mm]); header.setStyle(TableStyle([("ALIGN", (1,0), (1,0), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 8*mm)]))
    safe = lambda value: escape(str(value or ""))
    customer = document["customer"]; vehicle = document.get("vehicle")
    customer_text = f"<font size='8' color='#777777'>CUSTOMER</font><br/><b>{safe(customer.get('name'))}</b><br/>{safe(customer.get('business_name'))}<br/>{safe(customer.get('phone'))}<br/>{safe(customer.get('address'))}"
    vehicle_text = "<font size='8' color='#777777'>VEHICLE</font><br/>Not specified"
    if vehicle:
        vehicle_details = " / ".join(safe(x) for x in [vehicle.get("year"), vehicle.get("chassis_code"), vehicle.get("engine")] if x)
        vehicle_text = f"<font size='8' color='#777777'>VEHICLE</font><br/><b>BMW {safe(vehicle.get('model'))}</b><br/>{safe(vehicle.get('registration_number'))}<br/>{vehicle_details}"
    date_label = "ISSUE DATE" if document["type"] == "invoice" else "QUOTE DATE"
    date_text = f"<font size='8' color='#777777'>{date_label}</font><br/><b>{document['date']}</b>"
    if document.get("expiry_date"): date_text += f"<br/><br/><font size='8' color='#777777'>VALID UNTIL</font><br/><b>{document['expiry_date']}</b>"
    parties = Table([[Paragraph(customer_text, styles["BodyText"]), Paragraph(vehicle_text, styles["BodyText"]), Paragraph(date_text, styles["BodyText"])]], colWidths=[72*mm, 65*mm, 40*mm])
    parties.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f5f7f6")), ("BOX", (0,0), (-1,-1), .5, line), ("INNERGRID", (0,0), (-1,-1), .5, line), ("VALIGN", (0,0), (-1,-1), "TOP"), ("LEFTPADDING", (0,0), (-1,-1), 10), ("RIGHTPADDING", (0,0), (-1,-1), 10), ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10)]))
    rows = [["Description", "Qty", "Unit price", "Amount"]]
    for item in document["items"]:
        description = safe(item["description"]) + (f"\n{safe(item['warranty'])}" if item.get("warranty") else "")
        rows.append([description, str(item["quantity"]), f"LKR {item['unit_price_cents']/100:,.2f}", f"LKR {item['amount_cents']/100:,.2f}"])
    items = Table(rows, colWidths=[92*mm, 16*mm, 34*mm, 35*mm], repeatRows=1)
    items.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), dark), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8), ("ALIGN", (1,1), (-1,-1), "RIGHT"), ("GRID", (0,0), (-1,-1), .35, line), ("VALIGN", (0,0), (-1,-1), "TOP"), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fafafa")]), ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8)]))
    totals = []
    if document.get("discount_cents"): totals.append(["Discount", f"- LKR {document['discount_cents']/100:,.2f}"])
    if document.get("additional_charges_cents"): totals.append(["Additional charges", f"LKR {document['additional_charges_cents']/100:,.2f}"])
    totals.append(["TOTAL", f"LKR {document['total_cents']/100:,.2f}"])
    if document["type"] == "invoice": totals += [["Paid", f"LKR {document['paid_cents']/100:,.2f}"], ["BALANCE DUE", f"LKR {document['balance_cents']/100:,.2f}"]]
    total_table = Table(totals, colWidths=[42*mm, 43*mm], hAlign="RIGHT"); total_table.setStyle(TableStyle([("ALIGN", (1,0), (-1,-1), "RIGHT"), ("FONTNAME", (0,-1), (-1,-1), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 9), ("LINEABOVE", (0,-1), (-1,-1), .8, dark), ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    story = [header, parties, Spacer(1, 7*mm), items, Spacer(1, 5*mm), total_table]
    if document.get("notes"): story += [Spacer(1, 6*mm), Paragraph(f"<font size='8' color='#777777'>NOTES</font><br/>{safe(document['notes'])}", styles["BodyText"])]
    if qr_url:
        widget = qr.QrCodeWidget(qr_url); bounds = widget.getBounds(); size = 27*mm
        drawing = Drawing(size, size, transform=[size/(bounds[2]-bounds[0]), 0, 0, size/(bounds[3]-bounds[1]), 0, 0]); drawing.add(widget)
        qr_block = Table([[drawing, Paragraph("<b>Scan to view this secure digital document</b><br/><font size='8' color='#666666'>The QR code opens the customer copy. Supplier and purchase-cost information is never included.</font>", styles["BodyText"])]], colWidths=[32*mm, 120*mm], hAlign="LEFT")
        qr_block.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("BOX", (0,0), (-1,-1), .5, green), ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8), ("TOPPADDING", (0,0), (-1,-1), 8), ("BOTTOMPADDING", (0,0), (-1,-1), 8)])); story += [Spacer(1, 8*mm), qr_block]
    story += [Spacer(1, 9*mm), Paragraph("Thank you for choosing EMOTO BMW Spare Parts.<br/><br/>Authorized signature: ______________________________", styles["BodyText"])]
    pdf.build(story); return stream.getvalue()


@router.get("/quotations/{quotation_id}/pdf")
def download_quotation(quotation_id: int, request: Request, share_token: str | None = Query(None, max_length=200), user: User = Depends(require("quotations:manage")), db: DBSession = Depends(get_db)):
    document = customer_document(db, "quotation", quotation_id); qr_url = verified_share_url(db, request, "quotation", quotation_id, share_token)
    return StreamingResponse(BytesIO(document_pdf(document, qr_url)), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{document["number"]}.pdf"'})


@router.get("/invoices/{invoice_id}/pdf")
def download_invoice(invoice_id: int, request: Request, share_token: str | None = Query(None, max_length=200), user: User = Depends(require("invoices:view")), db: DBSession = Depends(get_db)):
    document = customer_document(db, "invoice", invoice_id); qr_url = verified_share_url(db, request, "invoice", invoice_id, share_token)
    return StreamingResponse(BytesIO(document_pdf(document, qr_url)), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{document["number"]}.pdf"'})


@router.post("/invoices/{invoice_id}/warranties", status_code=201)
def generate_warranties(invoice_id: int, user: User = Depends(require("warranties:manage")), db: DBSession = Depends(get_db)):
    invoice = db.scalar(select(Invoice).options(selectinload(Invoice.items)).where(Invoice.id == invoice_id))
    if not invoice: raise HTTPException(404, "Invoice not found")
    order = db.get(SalesOrder, invoice.order_id)
    created = []
    for item in invoice.items:
        existing = db.scalar(select(Warranty).where(Warranty.invoice_item_id == item.id))
        part = db.get(Part, item.part_id) if item.part_id else None
        if existing:
            created.append(existing); continue
        if not part or part.warranty_months <= 0:
            continue
        order_item = db.get(SalesOrderItem, item.order_item_id)
        warranty = Warranty(invoice_id=invoice.id, invoice_item_id=item.id, customer_id=invoice.customer_id, vehicle_id=order.vehicle_id, part_id=part.id, supplier_id=order_item.supplier_id if order_item else part.default_supplier_id, supplier_reference=order_item.supplier_reference if order_item else None, start_date=invoice.issue_date, expiry_date=add_months(invoice.issue_date, part.warranty_months), conditions=f"{part.warranty_months}-month parts warranty; subject to configured business terms")
        db.add(warranty); db.flush(); created.append(warranty)
    audit(db, user, "warranty.generate", "invoice", invoice.id, f"count={len(created)}"); db.commit()
    return [data(x) for x in created]


@router.get("/warranties")
def warranties(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(25, le=100), user: User = Depends(require("warranties:view")), db: DBSession = Depends(get_db)):
    return page(db, Warranty, q, [Warranty.status, Warranty.supplier_reference], page_no, size)


@router.post("/warranties/{warranty_id}/claims", status_code=201)
def warranty_claim(warranty_id: int, payload: ClaimIn, user: User = Depends(require("warranties:manage")), db: DBSession = Depends(get_db)):
    warranty = db.get(Warranty, warranty_id)
    if not warranty: raise HTTPException(404, "Warranty not found")
    claim = WarrantyClaim(warranty_id=warranty_id, details=payload.details); warranty.status = "Claim Open"
    db.add(claim); db.flush(); audit(db, user, "warranty.claim", "warranty_claim", claim.id); db.commit(); return data(claim)


@router.get("/reports/inventory/pdf")
def inventory_report_pdf(user: User = Depends(require("inventory:manage")), db: DBSession = Depends(get_db)):
    parts = db.scalars(select(Part).order_by(Part.category, Part.name)).all()
    total_cost = sum(part.physical_qty * part.purchase_cost_cents for part in parts)
    total_retail = sum(part.physical_qty * part.selling_price_cents for part in parts)
    low_count = sum(1 for part in parts if part.physical_qty - part.reserved_qty <= part.reorder_level)
    stream = BytesIO(); pdf = SimpleDocTemplate(stream, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm, title="EMOTO Inventory Report")
    styles = getSampleStyleSheet(); story = [Paragraph("<b>EMOTO</b> · BMW Spare Parts", styles["Title"]), Paragraph(f"Inventory valuation report · {date.today().isoformat()}", styles["Heading2"]), Spacer(1, 4*mm), Paragraph(f"SKUs: <b>{len(parts)}</b> &nbsp;&nbsp; Low stock: <b>{low_count}</b> &nbsp;&nbsp; Cost value: <b>LKR {total_cost/100:,.2f}</b> &nbsp;&nbsp; Retail value: <b>LKR {total_retail/100:,.2f}</b>", styles["BodyText"]), Spacer(1, 5*mm)]
    rows = [["SKU", "Part", "Fitment", "Location", "Physical", "Reserved", "Available", "Avg. cost", "Stock value", "Reorder"]]
    for part in parts:
        available = part.physical_qty - part.reserved_qty
        target = part.maximum_stock if part.maximum_stock is not None else part.reorder_level + part.reorder_quantity
        reorder = max(0, target - available) if available <= part.reorder_level else 0
        rows.append([part.sku, part.name, (part.fitment_notes or "-")[:35], " / ".join(x for x in [part.location, part.storage_bin] if x) or "-", part.physical_qty, part.reserved_qty, available, f"{part.purchase_cost_cents/100:,.2f}", f"{part.physical_qty*part.purchase_cost_cents/100:,.2f}", reorder or "-"])
    table = Table(rows, colWidths=[25*mm, 43*mm, 50*mm, 35*mm, 18*mm, 18*mm, 18*mm, 25*mm, 28*mm, 18*mm], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#171717")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7), ("GRID", (0,0), (-1,-1), .3, colors.HexColor("#dddddd")), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7f7f7")]), ("ALIGN", (4,1), (-1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "TOP"), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    story.append(table); pdf.build(story)
    return StreamingResponse(BytesIO(stream.getvalue()), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="EMOTO-inventory-{date.today().isoformat()}.pdf"'})


@router.get("/reports/financial")
def financial_report(start: date | None = None, end: date | None = None, user: User = Depends(require("reports:view")), db: DBSession = Depends(get_db)):
    conditions = []
    if start: conditions.append(Invoice.issue_date >= start)
    if end: conditions.append(Invoice.issue_date <= end)
    sales = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents), 0)).where(*conditions)) or 0
    costs = db.scalar(select(func.coalesce(func.sum(SalesOrderItem.cost_cents * SalesOrderItem.quantity), 0)).join(SalesOrder).join(Invoice, Invoice.order_id == SalesOrder.id).where(*conditions)) or 0
    expenses = db.scalar(select(func.coalesce(func.sum(SalesOrder.direct_expenses_cents), 0)).join(Invoice, Invoice.order_id == SalesOrder.id).where(*conditions)) or 0
    payment_conditions = []
    entry_conditions = []
    if start:
        payment_conditions.append(func.date(Payment.paid_at) >= start.isoformat()); entry_conditions.append(FinanceEntry.entry_date >= start)
    if end:
        payment_conditions.append(func.date(Payment.paid_at) <= end.isoformat()); entry_conditions.append(FinanceEntry.entry_date <= end)
    received = db.scalar(select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(*payment_conditions)) or 0
    other_income = db.scalar(select(func.coalesce(func.sum(FinanceEntry.amount_cents), 0)).where(FinanceEntry.entry_type == "income", *entry_conditions)) or 0
    operating_expenses = db.scalar(select(func.coalesce(func.sum(FinanceEntry.amount_cents), 0)).where(FinanceEntry.entry_type == "expense", *entry_conditions)) or 0
    outstanding = db.scalar(select(func.coalesce(func.sum(Invoice.total_cents - Invoice.paid_cents), 0)).where(Invoice.status != "Paid")) or 0
    methods = db.execute(select(Payment.method, func.sum(Payment.amount_cents)).where(*payment_conditions).group_by(Payment.method)).all()
    return {"net_sales_cents": sales, "purchase_costs_cents": costs, "direct_expenses_cents": expenses, "estimated_contribution_cents": sales-costs-expenses, "customer_payments_cents": received, "other_income_cents": other_income, "operating_expenses_cents": operating_expenses, "cash_inflow_cents": received+other_income, "net_cash_movement_cents": received+other_income-operating_expenses, "outstanding_cents": outstanding, "payment_methods": [{"method": row[0], "amount_cents": row[1]} for row in methods], "note": "Contribution is sales less captured item costs and direct order expenses. Cash movement uses recorded receipts, other income, and operating expenses; neither is audited net profit."}


@router.get("/finance/entries")
def finance_entries(q: str | None = None, page_no: int = Query(1, alias="page", ge=1), size: int = Query(50, le=100), user: User = Depends(require("reports:view")), db: DBSession = Depends(get_db)):
    return page(db, FinanceEntry, q, [FinanceEntry.category, FinanceEntry.description, FinanceEntry.reference], page_no, size)


@router.post("/finance/entries", status_code=201)
def finance_entry_create(payload: FinanceEntryIn, user: User = Depends(require("finance:manage")), db: DBSession = Depends(get_db)):
    entry = FinanceEntry(**payload.model_dump(), created_by=user.id)
    db.add(entry); db.flush(); audit(db, user, f"finance.{entry.entry_type}", "finance_entry", entry.id, f"amount_cents={entry.amount_cents}"); db.commit()
    return data(entry)


@router.get("/audit-logs")
def audit_logs(page_no: int = Query(1, alias="page", ge=1), size: int = Query(50, le=100), user: User = Depends(require("reports:view")), db: DBSession = Depends(get_db)):
    return page(db, AuditLog, None, [], page_no, size)


@router.get("/users")
def users(user: User = Depends(require("users:manage")), db: DBSession = Depends(get_db)):
    return [{**data(x, hide={"password_hash"})} for x in db.scalars(select(User).order_by(User.full_name))]


@router.post("/users", status_code=201)
def user_create(payload: UserIn, user: User = Depends(require("users:manage")), db: DBSession = Depends(get_db)):
    if payload.role not in {"Super Admin", "Sales", "Purchasing", "Inventory", "Accounts"}: raise HTTPException(422, "Invalid role")
    created = User(email=payload.email.lower(), full_name=payload.full_name, password_hash=hash_password(payload.password), role=payload.role)
    db.add(created)
    try: db.flush()
    except IntegrityError: raise HTTPException(409, "Email already exists")
    audit(db, user, "user.create", "user", created.id); db.commit(); return data(created, hide={"password_hash"})


@router.post("/attachments/{entity_type}/{entity_id}", status_code=201)
async def upload_attachment(entity_type: str, entity_id: int, file: UploadFile = File(...), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if entity_type not in {"supplier", "rfq", "customer", "vehicle", "invoice", "warranty"}: raise HTTPException(422, "Unsupported attachment target")
    if file.content_type not in SAFE_UPLOADS: raise HTTPException(415, "Only PDF, JPEG, PNG, and CSV files are accepted")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024: raise HTTPException(413, "File exceeds 10 MB limit")
    if file.content_type == "application/pdf" and not content.startswith(b"%PDF-"): raise HTTPException(415, "Invalid PDF content")
    if file.content_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"): raise HTTPException(415, "Invalid PNG content")
    if file.content_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"): raise HTTPException(415, "Invalid JPEG content")
    stored = secrets.token_hex(24) + SAFE_UPLOADS[file.content_type]
    (settings.data_path / "uploads" / stored).write_bytes(content)
    attachment = Attachment(entity_type=entity_type, entity_id=entity_id, original_name=Path(file.filename or "file").name[:255], stored_name=stored, content_type=file.content_type, size_bytes=len(content), uploaded_by=user.id)
    db.add(attachment); db.flush(); audit(db, user, "attachment.upload", entity_type, entity_id); db.commit(); return data(attachment)


@router.get("/attachments/{attachment_id}/download")
def attachment_download(attachment_id: int, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    attachment = db.get(Attachment, attachment_id)
    if not attachment: raise HTTPException(404, "Attachment not found")
    path = settings.data_path / "uploads" / attachment.stored_name
    if not path.is_file(): raise HTTPException(404, "Stored file is missing")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.original_name)


@router.post("/admin/backups", status_code=201)
def create_backup(user: User = Depends(require("backups:manage")), db: DBSession = Depends(get_db)):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"emoto-{stamp}-{secrets.token_hex(3)}.db"; target = settings.data_path / "backups" / filename
    source = sqlite3.connect(settings.data_path / "emoto.db"); destination = sqlite3.connect(target)
    try: source.backup(destination)
    finally: destination.close(); source.close()
    manifest = {"filename": filename, "created_at": datetime.now(timezone.utc).isoformat(), "size_bytes": target.stat().st_size, "created_by": user.id}
    (target.with_suffix(".json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    audit(db, user, "backup.create", details=filename); db.commit(); return manifest


@router.get("/admin/backups")
def list_backups(user: User = Depends(require("backups:manage"))):
    manifests = []
    for path in sorted((settings.data_path / "backups").glob("*.json"), reverse=True):
        try: manifests.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError): continue
    return manifests


@router.get("/admin/backups/{filename}/download")
def download_backup(filename: str, user: User = Depends(require("backups:manage"))):
    safe = Path(filename).name
    if safe != filename or not safe.endswith(".db"): raise HTTPException(400, "Invalid backup filename")
    path = settings.data_path / "backups" / safe
    if not path.is_file(): raise HTTPException(404, "Backup not found")
    return FileResponse(path, media_type="application/octet-stream", filename=safe)
