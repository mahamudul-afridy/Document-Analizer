"""End-to-end API tests: auth/RBAC, upload -> background job -> extraction -> validation ->
cross-verification -> corrections -> search -> analytics, plus failure scenarios."""
from decimal import Decimal

import pytest

from app.processing.ocr import tesseract_available

API = "/api/v1"


def upload(client, headers, fixtures_dir, *names, force=False):
    files = [("files", (n, (fixtures_dir / n).read_bytes())) for n in names]
    r = client.post(f"{API}/documents/upload", headers=headers, files=files, params={"force": force})
    assert r.status_code == 200, r.text
    return r.json()


def doc_detail(client, headers, doc_id):
    r = client.get(f"{API}/documents/{doc_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- auth
def test_setup_only_once(client, admin_headers):
    r = client.post(f"{API}/auth/setup", json={"email": "x@example.com", "password": "Another#123",
                                               "full_name": "X"})
    assert r.status_code == 409


def test_login_and_me(client, admin_headers):
    r = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "Admin#12345"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    assert client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "nope"}).status_code == 401


def test_requires_auth(client):
    assert client.get(f"{API}/documents").status_code == 401


def test_viewer_cannot_upload_or_change_settings(client, admin_headers, fixtures_dir):
    r = client.post(f"{API}/users", headers=admin_headers, json={"email": "viewer@example.com", "full_name": "V",
                                                                 "password": "Viewer#123", "role": "viewer"})
    assert r.status_code == 201
    tok = client.post(f"{API}/auth/login", json={"email": "viewer@example.com", "password": "Viewer#123"}).json()
    vh = {"Authorization": f"Bearer {tok['access_token']}"}
    files = [("files", ("a.pdf", (fixtures_dir / "invoice_05_minimal.pdf").read_bytes()))]
    assert client.post(f"{API}/documents/upload", headers=vh, files=files).status_code == 403
    assert client.put(f"{API}/settings/ai", headers=vh, json={"llm_enabled": False}).status_code == 403
    assert client.get(f"{API}/documents", headers=vh).status_code == 200


# ---------------------------------------------------------------- processing
def test_upload_process_extract_validate(client, admin_headers, fixtures_dir, manifest):
    res = upload(client, admin_headers, fixtures_dir, "invoice_00_classic.pdf")
    assert res[0]["ok"], res
    d = doc_detail(client, admin_headers, res[0]["document_id"])
    assert d["status"] in ("completed", "needs_review"), d
    stages = [h["stage"] for h in d["jobs"][0]["history"] if h["status"] == "completed"]
    assert stages == ["uploaded", "classification", "text_extraction", "ai_extraction", "validation",
                      "cross_verification", "completed"]
    inv = d["invoices_detail"][0]
    gt = manifest["invoice_00_classic.pdf"]
    assert inv["invoice_number"] == gt["invoice_number"]
    assert Decimal(inv["total"]) == Decimal(gt["total"])
    assert inv["engine"] == "builtin"
    assert len(inv["line_items"]) == len(gt["line_items"])


def test_identical_file_is_not_processed_twice(client, admin_headers, fixtures_dir):
    res = upload(client, admin_headers, fixtures_dir, "invoice_00_classic.pdf")
    assert not res[0]["ok"] and res[0]["duplicate_of"]


def test_duplicate_invoice_detected(client, admin_headers, fixtures_dir):
    # force=True: even if the bytes were identical, the invoice-level duplicate check must still fire
    res = upload(client, admin_headers, fixtures_dir, "invoice_00_duplicate.pdf", force=True)
    inv = doc_detail(client, admin_headers, res[0]["document_id"])["invoices_detail"][0]
    rules = {(v["rule"], v["severity"]) for v in inv["validations"]}
    assert ("duplicate_invoice", "failed") in rules


def test_tax_and_total_errors_detected(client, admin_headers, fixtures_dir):
    res = upload(client, admin_headers, fixtures_dir, "invoice_01_tax.pdf", "invoice_02_minimal.pdf")
    tax_inv = doc_detail(client, admin_headers, res[0]["document_id"])["invoices_detail"][0]
    assert any(v["rule"] == "tax_calculation" and v["severity"] == "failed" for v in tax_inv["validations"])
    tot_inv = doc_detail(client, admin_headers, res[1]["document_id"])["invoices_detail"][0]
    assert any(v["rule"] == "invoice_total" and v["severity"] == "failed" for v in tot_inv["validations"])
    assert tot_inv["validation_status"] == "failed"


def test_pdf_to_excel_cross_verification(client, admin_headers, fixtures_dir):
    upload(client, admin_headers, fixtures_dir, "invoice_03_classic.pdf")
    res = upload(client, admin_headers, fixtures_dir, "invoice_03_mismatch.xlsx")
    d = doc_detail(client, admin_headers, res[0]["document_id"])
    total_cmp = [c for c in d["cross_verification"] if c["field"] == "total"]
    assert total_cmp and total_cmp[0]["comparison_type"] == "pdf_excel" and not total_cmp[0]["is_match"]
    assert total_cmp[0]["difference"] in ("-50.00", "50.00")


def test_excel_to_csv_cross_verification(client, admin_headers, fixtures_dir):
    upload(client, admin_headers, fixtures_dir, "invoice_00.xlsx")
    res = upload(client, admin_headers, fixtures_dir, "register.csv")
    d = doc_detail(client, admin_headers, res[0]["document_id"])
    assert len(d["invoices_detail"]) == 6
    types = {c["comparison_type"] for c in d["cross_verification"]}
    assert "excel_csv" in types and "pdf_csv" in types


def test_manual_correction_is_audited_and_revalidated(client, admin_headers, fixtures_dir):
    docs = client.get(f"{API}/documents", headers=admin_headers, params={"q": "invoice_02_minimal"}).json()
    inv_id = docs["items"][0]["invoices"][0]["id"]
    inv = client.get(f"{API}/invoices/{inv_id}", headers=admin_headers).json()
    correct_total = str(Decimal(inv["subtotal"]) + Decimal(inv["tax"]))
    r = client.patch(f"{API}/invoices/{inv_id}", headers=admin_headers,
                     json={"total": correct_total, "reason": "Typo on printed invoice"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert Decimal(body["total"]) == Decimal(correct_total)
    assert body["corrections"][0]["field_path"] == "total"
    assert body["raw_extraction"]["total"] != correct_total  # original engine output preserved
    assert not any(v["rule"] == "invoice_total" and v["severity"] == "failed" for v in body["validations"])


def test_review_workflow(client, admin_headers):
    items = client.get(f"{API}/validation/results", headers=admin_headers, params={"severity": "failed"}).json()
    assert items["total"] > 0
    rid = items["items"][0]["id"]
    r = client.patch(f"{API}/validation/results/{rid}", headers=admin_headers,
                     json={"review_status": "approved", "note": "Checked with supplier"})
    assert r.status_code == 200 and r.json()["review_status"] == "approved"


def test_corrupt_file_fails_cleanly(client, admin_headers, tmp_path):
    files = [("files", ("broken.pdf", b"%PDF-1.4\n%%EOF garbage"))]
    res = client.post(f"{API}/documents/upload", headers=admin_headers, files=files).json()
    d = doc_detail(client, admin_headers, res[0]["document_id"])
    assert d["status"] == "failed" and d["error"]
    assert d["jobs"][0]["status"] == "failed"
    # retry endpoint creates a new job (which fails again, deterministically)
    r = client.post(f"{API}/jobs/{d['jobs'][0]['id']}/retry", headers=admin_headers)
    assert r.status_code == 200


def test_rejects_wrong_file_type(client, admin_headers):
    res = client.post(f"{API}/documents/upload", headers=admin_headers,
                      files=[("files", ("x.exe", b"MZ"))]).json()
    assert not res[0]["ok"] and "Unsupported" in res[0]["error"]


@pytest.mark.skipif(not tesseract_available(), reason="Tesseract not installed")
def test_scanned_image_ocr(client, admin_headers, fixtures_dir, manifest):
    name = next(n for n in manifest if n.endswith(("_scan.png", "_scan.jpg", "_scan.tiff")))
    res = upload(client, admin_headers, fixtures_dir, name, force=True)
    d = doc_detail(client, admin_headers, res[0]["document_id"])
    assert d["status"] in ("completed", "needs_review"), d["error"]
    assert d["page_texts"][0]["method"] == "tesseract"
    assert d["invoices_detail"][0]["total"] is not None


# ---------------------------------------------------------------- search / analytics / settings
def test_keyword_search(client, admin_headers, manifest):
    gt = manifest["invoice_00_classic.pdf"]
    r = client.get(f"{API}/search/keyword", headers=admin_headers, params={"invoice_number": gt["invoice_number"]})
    assert r.status_code == 200 and r.json()["total"] >= 1


def test_semantic_search_interprets_query(client, admin_headers):
    r = client.post(f"{API}/search/semantic", headers=admin_headers,
                    json={"query": "Show invoices with inconsistent tax calculations"})
    assert r.status_code == 200
    body = r.json()
    assert "tax_calculation" in body["interpretation"]["rules"]
    assert body["invoices"] and all(i["source"]["document_id"] for i in body["invoices"])


def test_analytics_overview(client, admin_headers):
    r = client.get(f"{API}/analytics/overview", headers=admin_headers).json()
    assert r["kpis"]["total_documents"] >= 5 and r["kpis"]["invoices_extracted"] >= 5
    assert len(r["activity"]) == 30


def test_ai_settings_without_key(client, admin_headers):
    r = client.get(f"{API}/settings/ai", headers=admin_headers).json()
    assert r["active_engine"] == "builtin" and r["api_key_set"] is False
    bad = client.put(f"{API}/settings/ai", headers=admin_headers, json={"llm_enabled": True, "provider": "openai"})
    assert bad.status_code == 400
    ok = client.put(f"{API}/settings/ai", headers=admin_headers,
                    json={"llm_enabled": False, "provider": "anthropic", "api_key": "sk-ant-test-123456789"}).json()
    assert ok["api_key_set"] and ok["api_key_masked"] == "sk-a…6789" and ok["active_engine"] == "builtin"


def test_api_key_auth(client, admin_headers):
    created = client.post(f"{API}/api-keys", headers=admin_headers, json={"name": "ci"}).json()
    assert client.get(f"{API}/documents", headers={"X-API-Key": created["key"]}).status_code == 200
    client.delete(f"{API}/api-keys/{created['id']}", headers=admin_headers)
    assert client.get(f"{API}/documents", headers={"X-API-Key": created["key"]}).status_code == 401


def test_download_json_and_delete(client, admin_headers, fixtures_dir):
    res = upload(client, admin_headers, fixtures_dir, "invoice_09_classic.pdf")
    did = res[0]["document_id"]
    j = client.get(f"{API}/documents/{did}/json", headers=admin_headers)
    assert j.status_code == 200 and j.json()["invoices"][0]["invoice_number"]
    assert client.get(f"{API}/documents/{did}/pages/1/image", headers=admin_headers).headers["content-type"] == \
        "image/png"
    assert client.delete(f"{API}/documents/{did}", headers=admin_headers).status_code == 200
    assert client.get(f"{API}/documents/{did}", headers=admin_headers).status_code == 404
