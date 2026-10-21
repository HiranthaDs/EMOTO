def post(admin, path, payload=None):
    return admin["client"].post(f"/api/v1{path}", json=payload or {}, headers=admin["headers"])


def test_supplier_to_payment_and_warranty_workflow(admin):
    supplier = post(admin, "/suppliers", {"company_name": "Berlin Parts GmbH", "country": "Germany"})
    assert supplier.status_code == 201
    customer = post(admin, "/customers", {"full_name": "Nimal Perera", "phone": "+94770000000"})
    assert customer.status_code == 201
    customer_id = customer.json()["id"]
    vehicle = post(admin, "/vehicles", {"customer_id": customer_id, "brand": "BMW", "model": "320d", "year": 2018})
    assert vehicle.status_code == 201
    part = post(admin, "/parts", {"sku": "BMW-BRK-001", "name": "Front brake pad set", "brand": "ATE", "default_supplier_id": supplier.json()["id"], "purchase_cost_cents": 2000000, "selling_price_cents": 2750000, "reorder_level": 2, "warranty_months": 12})
    assert part.status_code == 201, part.text
    part_id = part.json()["id"]
    stock = post(admin, "/inventory/movements", {"part_id": part_id, "movement_type": "receive", "quantity": 10, "supplier_id": supplier.json()["id"], "unit_cost_cents": 2000000, "document_reference": "OPENING-001", "notes": "Opening receipt"})
    assert stock.status_code == 201
    rfq = post(admin, "/rfqs", {"customer_id": customer_id, "supplier_ids": [supplier.json()["id"]], "items": [{"part_id": part_id, "description": "Front brake pad set", "quantity": 2}]})
    assert rfq.status_code == 201
    detail = admin["client"].get(f"/api/v1/rfqs/{rfq.json()['id']}")
    item_id = detail.json()["items"][0]["id"]
    offer = post(admin, f"/rfqs/{rfq.json()['id']}/quotes", {"supplier_id": supplier.json()["id"], "currency": "LKR", "lead_time_days": 7, "items": [{"rfq_item_id": item_id, "unit_price_cents": 2000000, "available_quantity": 5}]})
    assert offer.status_code == 201, offer.text
    selected = post(admin, f"/rfqs/{rfq.json()['id']}/quotes/{offer.json()['id']}/select")
    assert selected.status_code == 200
    quote = post(admin, "/quotations", {"customer_id": customer_id, "vehicle_id": vehicle.json()["id"], "items": [{"part_id": part_id, "description": "Front brake pad set", "quantity": 2, "unit_price_cents": 2750000}]})
    assert quote.status_code == 201
    assert post(admin, f"/quotations/{quote.json()['id']}/approve").status_code == 200
    order = post(admin, f"/quotations/{quote.json()['id']}/convert")
    assert order.status_code == 201
    parts = admin["client"].get("/api/v1/parts").json()["items"]
    assert parts[0]["reserved_qty"] == 2
    assert post(admin, f"/orders/{order.json()['id']}/dispatch").status_code == 200
    invoice = post(admin, f"/orders/{order.json()['id']}/invoice")
    assert invoice.status_code == 201
    invoice_id = invoice.json()["id"]
    first_payment = post(admin, f"/invoices/{invoice_id}/payments", {"amount_cents": 2000000, "method": "Bank transfer"})
    assert first_payment.json()["invoice"]["status"] == "Partially Paid"
    balance = invoice.json()["total_cents"] - 2000000
    paid = post(admin, f"/invoices/{invoice_id}/payments", {"amount_cents": balance, "method": "Cash"})
    assert paid.json()["invoice"]["status"] == "Paid"
    warranties = post(admin, f"/invoices/{invoice_id}/warranties")
    assert warranties.status_code == 201
    assert len(warranties.json()) == 1
    assert admin["client"].get(f"/api/v1/invoices/{invoice_id}/pdf").headers["content-type"] == "application/pdf"


def test_inventory_never_goes_negative(admin):
    part = post(admin, "/parts", {"sku": "SAFE-001", "name": "Safety stock item", "selling_price_cents": 1000})
    result = post(admin, "/inventory/movements", {"part_id": part.json()["id"], "movement_type": "issue", "quantity": 1})
    assert result.status_code == 409


def test_inventory_weighted_cost_snapshots_and_stocktake_protection(admin):
    supplier = post(admin, "/suppliers", {"company_name": "Stock Source GmbH"}).json()
    part = post(admin, "/parts", {
        "sku": "VALUED-001", "name": "Valued inventory item", "purchase_cost_cents": 1000,
        "reorder_level": 5, "reorder_quantity": 10, "maximum_stock": 25,
        "location": "Main warehouse", "storage_bin": "A-04",
    }).json()

    first = post(admin, "/inventory/movements", {
        "part_id": part["id"], "movement_type": "receive", "quantity": 10,
        "supplier_id": supplier["id"], "unit_cost_cents": 1000,
        "document_reference": "INV-100", "batch_number": "BATCH-A", "location": "Main warehouse",
    })
    assert first.status_code == 201, first.text
    assert first.json()["movement"]["quantity_before"] == 0
    assert first.json()["movement"]["quantity_after"] == 10
    assert first.json()["movement"]["total_cost_cents"] == 10000

    second = post(admin, "/inventory/movements", {
        "part_id": part["id"], "movement_type": "receive", "quantity": 10,
        "supplier_id": supplier["id"], "unit_cost_cents": 2000, "document_reference": "INV-101",
    })
    assert second.status_code == 201, second.text
    assert second.json()["part"]["purchase_cost_cents"] == 1500
    assert second.json()["part"]["stock_value_cents"] == 30000

    reserve = post(admin, "/inventory/movements", {"part_id": part["id"], "movement_type": "reserve", "quantity": 5, "notes": "Reserved for counter sale"})
    assert reserve.status_code == 201
    assert reserve.json()["movement"]["reserved_before"] == 0
    assert reserve.json()["movement"]["reserved_after"] == 5

    protected = post(admin, "/inventory/movements", {"part_id": part["id"], "movement_type": "stocktake", "counted_quantity": 4, "notes": "Count variance"})
    assert protected.status_code == 409

    counted = post(admin, "/inventory/movements", {"part_id": part["id"], "movement_type": "stocktake", "counted_quantity": 18, "notes": "Monthly stock count"})
    assert counted.status_code == 201, counted.text
    assert counted.json()["movement"]["quantity_delta"] == -2
    assert counted.json()["part"]["physical_qty"] == 18
    assert counted.json()["part"]["stock_value_cents"] == 27000

    overview = admin["client"].get("/api/v1/inventory/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["summary"]["stock_value_cents"] == 27000
    assert overview.json()["movements"][0]["created_by_name"] == "Test Admin"
    assert overview.json()["movements"][-1]["supplier_name"] == "Stock Source GmbH"


def test_backup_is_valid_sqlite(admin):
    backup = post(admin, "/admin/backups")
    assert backup.status_code == 201
    assert backup.json()["filename"].endswith(".db")


def test_customer_vehicle_supplier_history_and_public_quote(admin):
    profile = post(admin, "/customer-profiles", {
        "customer": {
            "full_name": "Kasun Silva",
            "business_name": "KS Motors",
            "phone": "+94771234567",
            "whatsapp": "+94771234567",
            "email": "kasun@example.com",
            "nic_tax_id": "VAT-123",
            "address": "Colombo",
            "billing_address": "Colombo 03",
            "preferred_contact": "WhatsApp",
        },
        "vehicle": {
            "registration_number": "cab-1234",
            "model": "520d",
            "year": 2019,
            "chassis_code": "G30",
            "engine": "B47D20",
            "vin": "WBATESTVIN1234567",
            "color": "Black",
            "mileage_km": 88000,
        },
    })
    assert profile.status_code == 201, profile.text
    customer_id = profile.json()["customer"]["id"]
    vehicle_id = profile.json()["vehicle"]["id"]
    assert profile.json()["vehicle"]["registration_number"] == "CAB-1234"

    duplicate = post(admin, "/customer-profiles", {
        "customer": {"full_name": "Duplicate Owner", "phone": "+94770000001"},
        "vehicle": {"registration_number": "CAB-1234", "model": "X5"},
    })
    assert duplicate.status_code == 409

    supplier = post(admin, "/suppliers", {
        "company_name": "Munich OEM GmbH",
        "business_registration": "HRB 12345",
        "contact_person": "Anna Keller",
        "country": "Germany",
        "phone": "+4989123456",
        "email": "sales@munich-oem.example",
        "supplier_reference": "MUC-OEM",
        "preferred_currency": "EUR",
        "typical_lead_time_days": 9,
        "payment_terms": "30 days",
        "bank_details": "Private bank details",
    })
    part = post(admin, "/parts", {
        "sku": "BMW-G30-FLT",
        "name": "G30 oil filter",
        "brand": "BMW",
        "purchase_cost_cents": 800000,
        "selling_price_cents": 1200000,
    })
    quote = post(admin, "/quotations", {
        "customer_id": customer_id,
        "vehicle_id": vehicle_id,
        "discount_cents": 100000,
        "additional_charges_cents": 50000,
        "items": [{
            "part_id": part.json()["id"],
            "supplier_id": supplier.json()["id"],
            "supplier_reference": "PO-MUC-7788",
            "description": "BMW G30 oil filter",
            "quantity": 2,
            "unit_cost_cents": 800000,
            "unit_price_cents": 1200000,
            "warranty": "12 months",
        }],
    })
    assert quote.status_code == 201, quote.text
    assert quote.json()["total_cents"] == 2350000

    supplier_profile = admin["client"].get(f"/api/v1/suppliers/{supplier.json()['id']}")
    assert supplier_profile.status_code == 200
    assert supplier_profile.json()["bank_details"] == "Private bank details"
    assert supplier_profile.json()["allocated_quotation_items"] == 1

    internal = admin["client"].get(f"/api/v1/quotations/{quote.json()['id']}")
    assert internal.json()["items"][0]["supplier"]["company_name"] == "Munich OEM GmbH"
    assert internal.json()["items"][0]["unit_cost_cents"] == 800000
    assert "bank_details" not in internal.json()["items"][0]["supplier"]

    customer = admin["client"].get(f"/api/v1/customers/{customer_id}").json()
    assert customer["vehicles"][0]["registration_number"] == "CAB-1234"
    assert customer["quotations"][0]["items"][0]["supplier_reference"] == "PO-MUC-7788"

    shared = post(admin, f"/quotations/{quote.json()['id']}/share", {"expires_days": 30})
    assert shared.status_code == 201, shared.text
    token = shared.json()["url"].rsplit("/", 1)[-1]
    public = admin["client"].get(f"/api/v1/public/shares/{token}")
    assert public.status_code == 200, public.text
    assert public.json()["customer"]["name"] == "Kasun Silva"
    assert public.json()["vehicle"]["registration_number"] == "CAB-1234"
    assert public.json()["items"][0]["amount_cents"] == 2400000
    assert "supplier" not in public.text.lower()
    assert "unit_cost_cents" not in public.text


def test_finance_report_separates_sales_cash_and_manual_entries(admin):
    income = post(admin, "/finance/entries", {
        "entry_date": "2026-10-21",
        "entry_type": "income",
        "category": "Delivery income",
        "amount_cents": 250000,
        "payment_method": "Cash",
        "description": "Customer delivery charge",
    })
    expense = post(admin, "/finance/entries", {
        "entry_date": "2026-10-21",
        "entry_type": "expense",
        "category": "Rent",
        "amount_cents": 100000,
        "payment_method": "Bank transfer",
        "description": "Workshop rent",
    })
    assert income.status_code == 201 and expense.status_code == 201

    report = admin["client"].get("/api/v1/reports/financial?start=2026-10-01&end=2026-10-31")
    assert report.status_code == 200, report.text
    values = report.json()
    assert values["net_sales_cents"] == 0
    assert values["customer_payments_cents"] == 0
    assert values["other_income_cents"] == 250000
    assert values["operating_expenses_cents"] == 100000
    assert values["cash_inflow_cents"] == 250000
    assert values["net_cash_movement_cents"] == 150000
