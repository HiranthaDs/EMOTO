from datetime import date
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BootstrapIn(BaseModel):
    token: str
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: str


class SupplierIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=180)
    contact_person: str | None = None
    phone: str | None = None
    whatsapp: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    country: str | None = None
    supplier_reference: str | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    business_registration: str | None = None
    website: str | None = None
    preferred_currency: str = Field("EUR", min_length=3, max_length=3)
    typical_lead_time_days: int | None = Field(None, ge=0, le=365)
    bank_details: str | None = None
    notes: str | None = None
    status: str = "Active"


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=180)
    phone: str = Field(min_length=3, max_length=40)
    whatsapp: str | None = None
    email: EmailStr | None = None
    address: str | None = None
    business_name: str | None = None
    nic_tax_id: str | None = None
    billing_address: str | None = None
    preferred_contact: str = "WhatsApp"
    notes: str | None = None
    status: str = "Active"


class VehicleIn(BaseModel):
    customer_id: int
    brand: str
    model: str
    chassis_code: str | None = None
    year: int | None = Field(None, ge=1900, le=2100)
    engine: str | None = None
    registration_number: str | None = None
    vin: str | None = None
    color: str | None = None
    mileage_km: int | None = Field(None, ge=0)
    notes: str | None = None


class PartIn(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=2, max_length=180)
    description: str | None = None
    category: str | None = None
    brand: str | None = None
    manufacturer_reference: str | None = None
    oem_reference: str | None = None
    fitment_notes: str | None = None
    barcode: str | None = None
    unit_of_measure: str = "Each"
    condition: str = "New"
    country_of_origin: str | None = None
    default_supplier_id: int | None = None
    purchase_cost_cents: int = Field(0, ge=0)
    last_purchase_cost_cents: int = Field(0, ge=0)
    selling_price_cents: int = Field(0, ge=0)
    reorder_level: int = Field(0, ge=0)
    reorder_quantity: int = Field(0, ge=0)
    maximum_stock: int | None = Field(None, ge=0)
    location: str | None = None
    storage_bin: str | None = None
    warranty_months: int = Field(0, ge=0, le=120)
    status: str = "Active"

    @model_validator(mode="after")
    def validate_stock_levels(self):
        if self.maximum_stock is not None and self.maximum_stock < self.reorder_level:
            raise ValueError("Maximum stock must be greater than or equal to the reorder level")
        return self


class MovementIn(BaseModel):
    part_id: int
    movement_type: str
    quantity: int | None = Field(None, gt=0)
    counted_quantity: int | None = Field(None, ge=0)
    movement_date: date = Field(default_factory=date.today)
    supplier_id: int | None = None
    unit_cost_cents: int | None = Field(None, ge=0)
    overhead_cost_cents: int = Field(0, ge=0)
    document_reference: str | None = Field(None, max_length=100)
    batch_number: str | None = Field(None, max_length=100)
    location: str | None = Field(None, max_length=100)
    notes: str | None = None

    @field_validator("movement_type")
    @classmethod
    def valid_type(cls, value):
        if value not in {"receive", "adjust_add", "adjust_remove", "reserve", "release", "issue", "return", "supplier_return", "stocktake"}:
            raise ValueError("Unsupported movement type")
        return value

    @model_validator(mode="after")
    def validate_quantities(self):
        if self.movement_type == "stocktake" and self.counted_quantity is None:
            raise ValueError("Counted quantity is required for a stocktake")
        if self.movement_type != "stocktake" and self.quantity is None:
            raise ValueError("Quantity is required for this movement")
        if self.movement_type == "receive" and self.unit_cost_cents is None:
            raise ValueError("Unit purchase cost is required when receiving stock")
        return self


class RFQItemIn(BaseModel):
    part_id: int | None = None
    description: str
    quantity: int = Field(gt=0)
    fitment_details: str | None = None


class RFQIn(BaseModel):
    customer_id: int | None = None
    requested_delivery_date: date | None = None
    supplier_ids: list[int] = []
    items: list[RFQItemIn] = Field(min_length=1)
    notes: str | None = None


class SupplierQuoteItemIn(BaseModel):
    rfq_item_id: int
    unit_price_cents: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    lead_time_days: int | None = Field(None, ge=0)


class SupplierQuoteIn(BaseModel):
    supplier_id: int
    reference: str | None = None
    currency: str = "LKR"
    validity_date: date | None = None
    lead_time_days: int | None = Field(None, ge=0)
    warranty_terms: str | None = None
    notes: str | None = None
    items: list[SupplierQuoteItemIn] = Field(min_length=1)


class LineIn(BaseModel):
    part_id: int | None = None
    service_id: int | None = None
    supplier_id: int | None = None
    supplier_reference: str | None = None
    description: str
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(ge=0)
    unit_cost_cents: int = Field(0, ge=0)
    warranty: str | None = None
    warranty_days: int = Field(0, ge=0, le=3650)


class QuotationIn(BaseModel):
    customer_id: int
    vehicle_id: int | None = None
    expiry_date: date | None = None
    discount_cents: int = Field(0, ge=0)
    additional_charges_cents: int = Field(0, ge=0)
    notes: str | None = None
    items: list[LineIn] = Field(min_length=1)


class PaymentIn(BaseModel):
    amount_cents: int = Field(gt=0)
    method: str
    reference: str | None = None


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str | None = None
    description: str | None = None
    default_fee_cents: int = Field(0, ge=0)
    estimated_minutes: int | None = Field(None, ge=0)
    recommended_interval_km: int | None = Field(None, ge=0)
    recommended_interval_months: int | None = Field(None, ge=0, le=120)
    status: str = "Active"


class POSLineIn(BaseModel):
    item_type: str
    part_id: int | None = None
    service_id: int | None = None
    description: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(ge=0)
    warranty_days: int = Field(0, ge=0, le=3650)

    @model_validator(mode="after")
    def validate_source(self):
        if self.item_type not in {"part", "service", "manual"}:
            raise ValueError("Item type must be part, service, or manual")
        if self.item_type == "part" and (not self.part_id or self.service_id):
            raise ValueError("A part line must reference only one part")
        if self.item_type == "service" and (not self.service_id or self.part_id):
            raise ValueError("A service line must reference only one service")
        if self.item_type == "manual" and (self.part_id or self.service_id):
            raise ValueError("A manual line cannot reference a catalog item")
        return self


class POSCheckoutIn(BaseModel):
    customer_id: int
    vehicle_id: int | None = None
    lines: list[POSLineIn] = Field(min_length=1)
    service_fee_cents: int = Field(0, ge=0)
    discount_cents: int = Field(0, ge=0)
    payment_amount_cents: int = Field(0, ge=0)
    payment_method: str = "Cash"
    payment_reference: str | None = None
    service_date: date = Field(default_factory=date.today)
    odometer_km: int | None = Field(None, ge=0)
    technician: str | None = None
    next_service_date: date | None = None
    next_service_km: int | None = Field(None, ge=0)
    notes: str | None = None


class VehicleProfileIn(BaseModel):
    brand: str = "BMW"
    model: str
    chassis_code: str | None = None
    year: int | None = Field(None, ge=1900, le=2100)
    engine: str | None = None
    registration_number: str = Field(min_length=2, max_length=40)
    vin: str | None = None
    color: str | None = None
    mileage_km: int | None = Field(None, ge=0)
    notes: str | None = None


class CustomerVehicleIn(BaseModel):
    customer: CustomerIn
    vehicle: VehicleProfileIn


class ShareIn(BaseModel):
    expires_days: int = Field(30, ge=1, le=365)


class FinanceEntryIn(BaseModel):
    entry_date: date = Field(default_factory=date.today)
    entry_type: str
    category: str = Field(min_length=2, max_length=80)
    amount_cents: int = Field(gt=0)
    payment_method: str | None = None
    reference: str | None = None
    description: str = Field(min_length=2, max_length=255)

    @field_validator("entry_type")
    @classmethod
    def valid_entry_type(cls, value):
        if value not in {"income", "expense"}:
            raise ValueError("Entry type must be income or expense")
        return value


class ClaimIn(BaseModel):
    details: str = Field(min_length=3)


class SettingsIn(BaseModel):
    business_name: str = "EMOTO"
    address: str = ""
    phone: str = ""
    email: str = ""
    currency: str = "LKR"
