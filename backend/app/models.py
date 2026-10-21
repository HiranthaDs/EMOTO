from __future__ import annotations

from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="Sales", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship()


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    company_name: Mapped[str] = mapped_column(String(180), index=True)
    contact_person: Mapped[str | None] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(40))
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(80))
    supplier_reference: Mapped[str | None] = mapped_column(String(100))
    payment_terms: Mapped[str | None] = mapped_column(String(200))
    delivery_terms: Mapped[str | None] = mapped_column(String(200))
    business_registration: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(255))
    preferred_currency: Mapped[str] = mapped_column(String(3), default="EUR")
    typical_lead_time_days: Mapped[int | None] = mapped_column(Integer)
    bank_details: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Active", index=True)


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(180), index=True)
    phone: Mapped[str] = mapped_column(String(40), index=True)
    whatsapp: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    business_name: Mapped[str | None] = mapped_column(String(180))
    nic_tax_id: Mapped[str | None] = mapped_column(String(100), index=True)
    billing_address: Mapped[str | None] = mapped_column(Text)
    preferred_contact: Mapped[str] = mapped_column(String(20), default="WhatsApp")
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Active", index=True)
    vehicles: Mapped[list[Vehicle]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    brand: Mapped[str] = mapped_column(String(80), index=True)
    model: Mapped[str] = mapped_column(String(100), index=True)
    chassis_code: Mapped[str | None] = mapped_column(String(80), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    engine: Mapped[str | None] = mapped_column(String(100))
    registration_number: Mapped[str | None] = mapped_column(String(40), index=True)
    vin: Mapped[str | None] = mapped_column(String(50), index=True)
    color: Mapped[str | None] = mapped_column(String(50))
    mileage_km: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    customer: Mapped[Customer] = relationship(back_populates="vehicles")


class Part(Base, TimestampMixin):
    __tablename__ = "parts"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    brand: Mapped[str | None] = mapped_column(String(100), index=True)
    manufacturer_reference: Mapped[str | None] = mapped_column(String(100), index=True)
    oem_reference: Mapped[str | None] = mapped_column(String(100), index=True)
    fitment_notes: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(String(100), index=True)
    unit_of_measure: Mapped[str] = mapped_column(String(30), default="Each")
    condition: Mapped[str] = mapped_column(String(30), default="New")
    country_of_origin: Mapped[str | None] = mapped_column(String(80))
    default_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    purchase_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    last_purchase_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    selling_price_cents: Mapped[int] = mapped_column(Integer, default=0)
    physical_qty: Mapped[int] = mapped_column(Integer, default=0)
    reserved_qty: Mapped[int] = mapped_column(Integer, default=0)
    reorder_level: Mapped[int] = mapped_column(Integer, default=0)
    reorder_quantity: Mapped[int] = mapped_column(Integer, default=0)
    maximum_stock: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(80))
    storage_bin: Mapped[str | None] = mapped_column(String(80))
    warranty_months: Mapped[int] = mapped_column(Integer, default=0)
    last_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="Active", index=True)


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    movement_type: Mapped[str] = mapped_column(String(30), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    quantity_delta: Mapped[int] = mapped_column(Integer, default=0)
    reserved_delta: Mapped[int] = mapped_column(Integer, default=0)
    quantity_before: Mapped[int] = mapped_column(Integer, default=0)
    quantity_after: Mapped[int] = mapped_column(Integer, default=0)
    reserved_before: Mapped[int] = mapped_column(Integer, default=0)
    reserved_after: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    stock_value_before_cents: Mapped[int] = mapped_column(Integer, default=0)
    stock_value_after_cents: Mapped[int] = mapped_column(Integer, default=0)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    movement_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    document_reference: Mapped[str | None] = mapped_column(String(100), index=True)
    batch_number: Mapped[str | None] = mapped_column(String(100), index=True)
    location: Mapped[str | None] = mapped_column(String(100))
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RFQ(Base, TimestampMixin):
    __tablename__ = "purchase_rfqs"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    requested_delivery_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="Draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list[RFQItem]] = relationship(back_populates="rfq", cascade="all, delete-orphan")
    suppliers: Mapped[list[RFQSupplier]] = relationship(back_populates="rfq", cascade="all, delete-orphan")


class RFQItem(Base):
    __tablename__ = "rfq_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("purchase_rfqs.id", ondelete="CASCADE"), index=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    fitment_details: Mapped[str | None] = mapped_column(Text)
    rfq: Mapped[RFQ] = relationship(back_populates="items")


class RFQSupplier(Base):
    __tablename__ = "rfq_suppliers"
    __table_args__ = (UniqueConstraint("rfq_id", "supplier_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("purchase_rfqs.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    response_status: Mapped[str] = mapped_column(String(30), default="Awaiting")
    rfq: Mapped[RFQ] = relationship(back_populates="suppliers")


class SupplierQuote(Base, TimestampMixin):
    __tablename__ = "supplier_quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("purchase_rfqs.id"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    reference: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="LKR")
    validity_date: Mapped[date | None] = mapped_column(Date)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)
    warranty_terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list[SupplierQuoteItem]] = relationship(cascade="all, delete-orphan")


class SupplierQuoteItem(Base):
    __tablename__ = "supplier_quote_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_quote_id: Mapped[int] = mapped_column(ForeignKey("supplier_quotes.id", ondelete="CASCADE"), index=True)
    rfq_item_id: Mapped[int] = mapped_column(ForeignKey("rfq_items.id"))
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    available_quantity: Mapped[int] = mapped_column(Integer, default=0)
    lead_time_days: Mapped[int | None] = mapped_column(Integer)


class Quotation(Base, TimestampMixin):
    __tablename__ = "customer_quotations"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    quote_date: Mapped[date] = mapped_column(Date, default=date.today)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="Draft", index=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    additional_charges_cents: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list[QuotationItem]] = relationship(cascade="all, delete-orphan")


class QuotationItem(Base):
    __tablename__ = "customer_quotation_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(ForeignKey("customer_quotations.id", ondelete="CASCADE"), index=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_reference: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    unit_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    warranty: Mapped[str | None] = mapped_column(String(200))


class SalesOrder(Base, TimestampMixin):
    __tablename__ = "sales_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    quotation_id: Mapped[int | None] = mapped_column(ForeignKey("customer_quotations.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    status: Mapped[str] = mapped_column(String(40), default="Draft", index=True)
    direct_expenses_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    additional_charges_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    items: Mapped[list[SalesOrderItem]] = relationship(cascade="all, delete-orphan")


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True)
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    supplier_reference: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    fulfilled_qty: Mapped[int] = mapped_column(Integer, default=0)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("sales_orders.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    issue_date: Mapped[date] = mapped_column(Date, default=date.today)
    total_cents: Mapped[int] = mapped_column(Integer)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="Unpaid", index=True)
    items: Mapped[list[InvoiceItem]] = relationship(cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("sales_order_items.id"))
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"))
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(100))
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class FinanceEntry(Base, TimestampMixin):
    __tablename__ = "finance_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    entry_type: Mapped[str] = mapped_column(String(20), index=True)  # income or expense
    category: Mapped[str] = mapped_column(String(80), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    payment_method: Mapped[str | None] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class DocumentShare(Base):
    __tablename__ = "document_shares"
    __table_args__ = (UniqueConstraint("token_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_type: Mapped[str] = mapped_column(String(20), index=True)
    document_id: Mapped[int] = mapped_column(Integer, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Warranty(Base, TimestampMixin):
    __tablename__ = "warranties"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    invoice_item_id: Mapped[int] = mapped_column(ForeignKey("invoice_items.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    part_id: Mapped[int | None] = mapped_column(ForeignKey("parts.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    supplier_reference: Mapped[str | None] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date] = mapped_column(Date, index=True)
    conditions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Active", index=True)


class WarrantyClaim(Base, TimestampMixin):
    __tablename__ = "warranty_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    warranty_id: Mapped[int] = mapped_column(ForeignKey("warranties.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="Open", index=True)
    details: Mapped[str] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(Text)


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(80), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DocumentSequence(Base):
    __tablename__ = "document_sequences"
    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


Index("ix_parts_stock_alert", Part.status, Part.physical_qty, Part.reserved_qty, Part.reorder_level)
