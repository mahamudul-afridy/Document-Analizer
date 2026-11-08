"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-07
"""
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

STATEMENTS = [
    'CREATE EXTENSION IF NOT EXISTS vector',
    'CREATE EXTENSION IF NOT EXISTS pg_trgm',
    'CREATE TABLE users (\n\temail VARCHAR(255) NOT NULL, \n\tpassword_hash VARCHAR(255) NOT NULL, \n\tfull_name VARCHAR(255) NOT NULL, \n\trole VARCHAR(32) NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tlast_login_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (email)\n)',
    'CREATE TABLE api_keys (\n\tuser_id UUID NOT NULL, \n\tname VARCHAR(120) NOT NULL, \n\tkey_prefix VARCHAR(16) NOT NULL, \n\tkey_hash VARCHAR(64) NOT NULL, \n\tlast_used_at TIMESTAMP WITH TIME ZONE, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, \n\tUNIQUE (key_hash)\n)',
    'CREATE INDEX ix_api_keys_user_id ON api_keys (user_id)',
    'CREATE TABLE audit_logs (\n\tid BIGSERIAL NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tuser_id UUID, \n\taction VARCHAR(64) NOT NULL, \n\tentity_type VARCHAR(64), \n\tentity_id VARCHAR(64), \n\tip VARCHAR(64), \n\tuser_agent VARCHAR(255), \n\tdetails JSONB NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at)',
    'CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id)',
    'CREATE TABLE documents (\n\towner_id UUID, \n\toriginal_name VARCHAR(512) NOT NULL, \n\tfile_kind VARCHAR(32) NOT NULL, \n\tmime_type VARCHAR(128) NOT NULL, \n\tsize_bytes BIGINT NOT NULL, \n\tsha256 VARCHAR(64) NOT NULL, \n\tdoc_type VARCHAR(32), \n\tis_scanned BOOLEAN, \n\tpage_count INTEGER, \n\tstatus VARCHAR(32) NOT NULL, \n\terror TEXT, \n\tis_demo BOOLEAN NOT NULL, \n\tdeleted_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_documents_created_at ON documents (created_at)',
    'CREATE INDEX ix_documents_name_trgm ON documents USING gin (original_name gin_trgm_ops)',
    'CREATE INDEX ix_documents_owner_id ON documents (owner_id)',
    'CREATE INDEX ix_documents_sha256 ON documents (sha256)',
    'CREATE INDEX ix_documents_status ON documents (status)',
    'CREATE TABLE system_settings (\n\tkey VARCHAR(100) NOT NULL, \n\tvalue JSONB NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_by UUID, \n\tPRIMARY KEY (key), \n\tFOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE TABLE cross_verification_results (\n\tsource_document_id UUID NOT NULL, \n\ttarget_document_id UUID NOT NULL, \n\tcomparison_type VARCHAR(32) NOT NULL, \n\tmatch_basis VARCHAR(64) NOT NULL, \n\tfield VARCHAR(64) NOT NULL, \n\tsource_value VARCHAR(255), \n\ttarget_value VARCHAR(255), \n\tdifference VARCHAR(64), \n\tis_match BOOLEAN NOT NULL, \n\tseverity VARCHAR(32) NOT NULL, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(source_document_id) REFERENCES documents (id) ON DELETE CASCADE, \n\tFOREIGN KEY(target_document_id) REFERENCES documents (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_cross_verification_results_source_document_id ON cross_verification_results (source_document_id)',
    'CREATE INDEX ix_cross_verification_results_target_document_id ON cross_verification_results (target_document_id)',
    'CREATE TABLE document_files (\n\tdocument_id UUID NOT NULL, \n\trole VARCHAR(32) NOT NULL, \n\tstorage_key VARCHAR(512) NOT NULL, \n\tmime_type VARCHAR(128) NOT NULL, \n\tsize_bytes BIGINT NOT NULL, \n\tpage_no INTEGER, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_document_files_document_id ON document_files (document_id)',
    'CREATE TABLE extracted_text (\n\tdocument_id UUID NOT NULL, \n\tpage_no INTEGER NOT NULL, \n\tmethod VARCHAR(32) NOT NULL, \n\ttext TEXT NOT NULL, \n\twords JSONB, \n\twidth FLOAT, \n\theight FLOAT, \n\tocr_confidence FLOAT, \n\tembedding VECTOR(384), \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_extracted_text_doc_page UNIQUE (document_id, page_no), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_extracted_text_embedding ON extracted_text USING hnsw (embedding vector_cosine_ops)',
    'CREATE TABLE invoices (\n\tdocument_id UUID NOT NULL, \n\tsource_ref JSONB, \n\tinvoice_number VARCHAR(128), \n\tinvoice_number_norm VARCHAR(128), \n\tinvoice_date DATE, \n\tsupplier_name VARCHAR(255), \n\tcustomer_name VARCHAR(255), \n\tsubtotal NUMERIC(18, 4), \n\ttax NUMERIC(18, 4), \n\ttotal NUMERIC(18, 4), \n\tcurrency VARCHAR(8), \n\ttax_rate NUMERIC(7, 3), \n\tconfidence JSONB NOT NULL, \n\tfield_sources JSONB NOT NULL, \n\traw_extraction JSONB NOT NULL, \n\tengine VARCHAR(64) NOT NULL, \n\tvalidation_status VARCHAR(32) NOT NULL, \n\tneeds_review BOOLEAN NOT NULL, \n\tembedding VECTOR(384), \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_invoices_customer_trgm ON invoices USING gin (customer_name gin_trgm_ops)',
    'CREATE INDEX ix_invoices_document_id ON invoices (document_id)',
    'CREATE INDEX ix_invoices_embedding ON invoices USING hnsw (embedding vector_cosine_ops)',
    'CREATE INDEX ix_invoices_invoice_date ON invoices (invoice_date)',
    'CREATE INDEX ix_invoices_invoice_number_norm ON invoices (invoice_number_norm)',
    'CREATE INDEX ix_invoices_supplier_number ON invoices (supplier_name, invoice_number)',
    'CREATE INDEX ix_invoices_supplier_trgm ON invoices USING gin (supplier_name gin_trgm_ops)',
    'CREATE INDEX ix_invoices_total ON invoices (total)',
    'CREATE TABLE processing_jobs (\n\tdocument_id UUID NOT NULL, \n\tcelery_task_id VARCHAR(64), \n\tstatus VARCHAR(32) NOT NULL, \n\tcurrent_stage VARCHAR(64) NOT NULL, \n\tprogress INTEGER NOT NULL, \n\tattempts INTEGER NOT NULL, \n\terror TEXT, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_processing_jobs_status ON processing_jobs (status)',
    "CREATE UNIQUE INDEX uq_processing_jobs_active ON processing_jobs (document_id) WHERE status IN ('queued','running')",
    'CREATE TABLE invoice_line_items (\n\tinvoice_id UUID NOT NULL, \n\tposition INTEGER NOT NULL, \n\tdescription TEXT, \n\tquantity NUMERIC(18, 4), \n\tunit_price NUMERIC(18, 4), \n\ttax NUMERIC(18, 4), \n\tline_total NUMERIC(18, 4), \n\tconfidence FLOAT, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_invoice_line_items_invoice_id ON invoice_line_items (invoice_id)',
    'CREATE TABLE manual_corrections (\n\tinvoice_id UUID NOT NULL, \n\tuser_id UUID, \n\tfield_path VARCHAR(128) NOT NULL, \n\told_value TEXT, \n\tnew_value TEXT, \n\treason TEXT, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_manual_corrections_invoice_id ON manual_corrections (invoice_id)',
    'CREATE TABLE processing_history (\n\tjob_id UUID NOT NULL, \n\tstage VARCHAR(64) NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\tmessage TEXT, \n\tduration_ms INTEGER, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(job_id) REFERENCES processing_jobs (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_processing_history_job_id ON processing_history (job_id)',
    'CREATE TABLE validation_results (\n\tinvoice_id UUID NOT NULL, \n\trule VARCHAR(64) NOT NULL, \n\tfield VARCHAR(64), \n\tmessage TEXT NOT NULL, \n\texpected VARCHAR(255), \n\textracted VARCHAR(255), \n\tdifference VARCHAR(64), \n\tseverity VARCHAR(32) NOT NULL, \n\trelated_document_id UUID, \n\treview_status VARCHAR(32) NOT NULL, \n\treviewed_by UUID, \n\treviewed_at TIMESTAMP WITH TIME ZONE, \n\treview_note TEXT, \n\tid UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE, \n\tFOREIGN KEY(related_document_id) REFERENCES documents (id) ON DELETE SET NULL, \n\tFOREIGN KEY(reviewed_by) REFERENCES users (id) ON DELETE SET NULL\n)',
    'CREATE INDEX ix_validation_results_invoice_id ON validation_results (invoice_id)',
    'CREATE INDEX ix_validation_results_severity ON validation_results (severity)',
]

DROPS = [
    'DROP TABLE IF EXISTS validation_results CASCADE',
    'DROP TABLE IF EXISTS processing_history CASCADE',
    'DROP TABLE IF EXISTS manual_corrections CASCADE',
    'DROP TABLE IF EXISTS invoice_line_items CASCADE',
    'DROP TABLE IF EXISTS processing_jobs CASCADE',
    'DROP TABLE IF EXISTS invoices CASCADE',
    'DROP TABLE IF EXISTS extracted_text CASCADE',
    'DROP TABLE IF EXISTS document_files CASCADE',
    'DROP TABLE IF EXISTS cross_verification_results CASCADE',
    'DROP TABLE IF EXISTS system_settings CASCADE',
    'DROP TABLE IF EXISTS documents CASCADE',
    'DROP TABLE IF EXISTS audit_logs CASCADE',
    'DROP TABLE IF EXISTS api_keys CASCADE',
    'DROP TABLE IF EXISTS users CASCADE',
]


def upgrade() -> None:
    for sql in STATEMENTS:
        op.execute(sql)


def downgrade() -> None:
    for sql in DROPS:
        op.execute(sql)
