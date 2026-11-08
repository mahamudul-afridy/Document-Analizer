# Database schema (PostgreSQL 16 + pgvector + pg_trgm)

Source of truth: `backend/app/db/models.py`. Migration: `backend/alembic/versions/0001_initial.py`.
Every table has a UUID `id`, `created_at` and `updated_at` (except `audit_logs`, which uses a bigserial id). Money is stored as `NUMERIC(18,4)`. Enums are VARCHAR values.

```
users ─┬─< api_keys
       ├─< documents ─┬─< document_files
       │              ├─< extracted_text            (page text, word boxes, embedding vector(384))
       │              ├─< processing_jobs ─< processing_history
       │              └─< invoices ─┬─< invoice_line_items
       │                            ├─< validation_results ──> documents (related_document_id)
       │                            └─< manual_corrections ──> users
       ├─< audit_logs
       └─< system_settings (updated_by)
documents ─< cross_verification_results >─ documents   (source / target)
```

| Table | Key columns | Constraints and indexes |
|---|---|---|
| `users` | email, password_hash (argon2), full_name, role (admin/reviewer/viewer), is_active, last_login_at | unique email |
| `api_keys` | user_id, name, key_prefix, key_hash (sha256), last_used_at, revoked_at | unique key_hash |
| `system_settings` | key (PK), value JSONB (AI engine config, API key encrypted), updated_by | |
| `documents` | owner_id, original_name, file_kind, mime_type, size_bytes, sha256, doc_type, is_scanned, page_count, status, error, is_demo, deleted_at | idx sha256, status, created_at; GIN trigram on original_name |
| `document_files` | document_id, role (original/page_image), storage_key, mime_type, size_bytes | idx document_id |
| `extracted_text` | document_id, page_no, method (pdf_text/tesseract/sheet), text, words JSONB, ocr_confidence, embedding vector(384) | unique (document_id, page_no); HNSW cosine on embedding |
| `invoices` | document_id, source_ref, invoice_number, invoice_number_norm, invoice_date, supplier_name, customer_name, subtotal, tax, tax_rate, total, currency, confidence, field_sources, raw_extraction, engine, validation_status, needs_review, embedding | idx (supplier, number), number_norm, date, total; GIN trigram on supplier/customer; HNSW on embedding |
| `invoice_line_items` | invoice_id, position, description, quantity, unit_price, tax, line_total, confidence | idx invoice_id |
| `processing_jobs` | document_id, celery_task_id, status, current_stage, progress, attempts, error, started_at, finished_at | **partial unique index (document_id) WHERE status IN ('queued','running')** prevents duplicate processing |
| `processing_history` | job_id, stage, status, message, duration_ms | idx job_id |
| `validation_results` | invoice_id, rule, field, message, expected, extracted, difference, severity, related_document_id, review_status, reviewed_by, reviewed_at, review_note | idx invoice_id, severity |
| `cross_verification_results` | source_document_id, target_document_id, comparison_type, match_basis, field, source_value, target_value, difference, is_match, severity | idx source, target |
| `manual_corrections` | invoice_id, user_id, field_path, old_value, new_value, reason | idx invoice_id |
| `audit_logs` | user_id, action, entity_type, entity_id, ip, user_agent, details JSONB | idx created_at, (entity_type, entity_id) |

Deleting a document cascades to its files, pages, jobs, invoices, validations and cross-verification rows. `related_document_id` and `user_id` references are set to NULL.
