# Business assumptions

- LKR is the default display currency; supplier offers retain their declared three-letter currency.
- A quotation never reserves or deducts stock. Conversion to a confirmed order attempts reservation. Dispatch deducts both physical and reserved quantities.
- Warranty duration comes from the catalog part and starts on the invoice issue date. Terms remain configurable business wording; the system does not invent legal exclusions.
- Financial “estimated contribution” is sales less captured acquisition cost and direct order expenses. It is not audited net profit and excludes overheads unless explicitly recorded.
- OEM and vehicle fitment fields are reference data entered by staff. The application does not independently assert automotive compatibility.
- Dates are business dates; event timestamps are UTC and rendered in Asia/Colombo.
- SQLite deployment is intentionally single-instance/single-worker. Horizontal scaling requires a database architecture change.

