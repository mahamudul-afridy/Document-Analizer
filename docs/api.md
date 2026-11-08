# REST API

Interactive OpenAPI docs: **`/api/docs`** (Swagger) and **`/api/redoc`**. Base path: `/api/v1`.

**Authentication:** use `Authorization: Bearer <access_token>` (from `/auth/login`) or `X-API-Key: dm_…` (from API Management).
**Errors** are returned as `{"detail": "...", "errors"?: [{"field","message"}]}`. Status codes: 401 unauthenticated, 403 role too low, 404, 409 conflict, 422 validation, 429 rate-limited.
**Pagination:** `?page=1&page_size=20` returns `{items, total, page, page_size}`.

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/auth/setup-status` | public | Whether the first admin still needs to be created |
| POST | `/auth/setup` | public (once) | Create first admin |
| POST | `/auth/login` | public | Email + password → access token (+ refresh cookie) |
| POST | `/auth/refresh` · `/auth/logout` | cookie | Renew access token · clear cookie |
| GET/PATCH | `/auth/me` | any | Profile, change password |
| POST | `/documents/upload?force=` | reviewer | Multipart `files` (≤50 per request). Per-file result, job id, duplicate detection |
| GET | `/documents` | viewer | Filters: `q,status,file_kind,doc_type,validation_status,is_demo,date_from,date_to,sort` |
| GET | `/documents/{id}` | viewer | Detail: invoices, line items, validations, jobs + history, page text, cross-verification |
| GET | `/documents/{id}/file` | viewer | Download the original file |
| GET | `/documents/{id}/json` | viewer | Download the extracted JSON (with source references) |
| GET | `/documents/{id}/pages/{n}/image` · `/words` | viewer | Page preview PNG · OCR/PDF word boxes |
| POST | `/documents/{id}/reprocess` | reviewer | New processing job |
| DELETE | `/documents/{id}` | reviewer | Delete document, data and file (audited) |
| GET | `/jobs` · `/jobs/{id}` · `/jobs/counts` · `/jobs/stages` | viewer | Processing queue and status |
| GET | `/jobs/stream?token=` | viewer | **Server-Sent Events** with live stage progress |
| POST | `/jobs/{id}/retry` · `/jobs/retry-failed` · `/jobs/{id}/cancel` | reviewer | Retry failed jobs, cancel queued ones |
| GET | `/invoices` | viewer | Filters: `q,supplier,customer,status,currency,date_from,date_to,min_total,max_total,is_demo,sort` |
| GET | `/invoices/export` | viewer | CSV export (same filters) |
| GET | `/invoices/{id}` | viewer | Detail including corrections and raw engine output |
| PATCH | `/invoices/{id}` | reviewer | Manual correction (fields, line items, `clear_fields`, `reason`). Audited and re-validated |
| GET | `/validation/results` · `/validation/summary` | viewer | Results by severity, review status and rule |
| PATCH | `/validation/results/{id}` | reviewer | Review: `approved` / `rejected` / `pending` with an optional note |
| GET | `/verification` · `/verification/summary` | viewer | Cross-document field comparisons |
| POST | `/verification/run/{document_id}` | reviewer | Re-run validation and cross-verification without re-extracting |
| GET | `/search/keyword` | viewer | `q,invoice_number,supplier,customer,date_from,date_to,total,document_name` |
| POST | `/search/semantic` | viewer | `{"query": "..."}` → parsed filters + vector-ranked invoices + page snippets |
| GET | `/analytics/overview?days=&include_demo=` · `/analytics/recent-documents` | viewer | Dashboard data |
| GET/POST/DELETE | `/api-keys` | any | Manage own API keys (the key is shown once) |
| GET/PUT | `/settings/ai` · POST `/settings/ai/test` | viewer / admin | AI engine: enable LLM, provider, model, encrypted key, fallback |
| GET | `/settings/system` | viewer | Effective processing configuration |
| GET/POST/PATCH | `/users` | admin | User management and roles |
| GET | `/audit-logs` | admin | Audit trail |
| POST/DELETE | `/demo/load` · `/demo` | admin | Load or remove labelled sample data |
| GET | `/api/health` | public | DB and Redis health (503 when degraded) |

## Example: extracted invoice JSON (`/documents/{id}/json`)

```json
{
  "document": {"id": "…", "name": "invoice.pdf", "type": "invoice", "status": "completed"},
  "invoices": [{
    "invoice_number": "INV-2026-001", "invoice_date": "2026-10-15",
    "supplier_name": "ABC Corporation", "customer_name": "XYZ Limited",
    "subtotal": 1000.0, "tax": 150.0, "total": 1150.0, "currency": "USD",
    "line_items": [{"description": "Consulting", "quantity": 10, "unit_price": 100.0, "tax": null, "line_total": 1000.0}],
    "confidence": {"invoice_number": 0.95, "total": 0.97, "customer_name": 0.92},
    "validation_status": "passed", "engine": "builtin",
    "source_document": {"document_id": "…", "name": "invoice.pdf",
                        "field_sources": {"total": {"page": 1, "bbox": [0.71, 0.62, 0.9, 0.64], "text": "$1,150.00"}}}
  }]
}
```
