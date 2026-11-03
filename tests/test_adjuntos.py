"""HU-05: adjuntos (foto del ticket, PDF/XML de la factura) en cada gasto."""

from app.models.attachment import Attachment, AttachmentBlob
from app.models.period import PeriodLock
from app.services import attachments as storage
from tests.helpers import auth_headers, register

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
XML = b'<?xml version="1.0" encoding="UTF-8"?><cfdi:Comprobante Total="116.00"/>'


def _setup(client, email="dueno@example.com", business="Laboratorios La Fe"):
    body = register(client, email=email, business=business, initial_cash="5000")
    headers = auth_headers(body)
    category = client.get("/api/categories?kind=EXPENSE", headers=headers).json()[0]
    return headers, body["organization"]["id"], category


def _expense(client, headers, category, date="2026-10-15", description="Papelería"):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={"date": date, "description": description, "amount": "116.00", "category_id": category["id"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, headers, expense_id, filename, content, content_type):
    return client.post(
        f"/api/expenses/{expense_id}/attachments",
        headers=headers,
        files={"file": (filename, content, content_type)},
    )


def _list(client, headers, expense_id):
    return client.get(f"/api/expenses/{expense_id}/attachments", headers=headers)


def test_upload_pdf_png_and_xml(client):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)

    pdf = _upload(client, headers, expense["id"], "factura.pdf", PDF, "application/pdf")
    assert pdf.status_code == 201, pdf.text
    body = pdf.json()
    assert body["filename"] == "factura.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(PDF)
    assert body["uploaded_by_name"] == "Dueño"
    assert "data" not in body

    png = _upload(client, headers, expense["id"], "ticket.PNG", PNG, "image/png")
    assert png.status_code == 201, png.text
    xml = _upload(client, headers, expense["id"], "cfdi.xml", XML, "text/xml")
    assert xml.status_code == 201, xml.text
    assert xml.json()["content_type"] == "application/xml"
    # Teléfonos que no declaran tipo: decide la extensión + la firma.
    jpg = _upload(client, headers, expense["id"], "foto.jpg", JPEG, "application/octet-stream")
    assert jpg.status_code == 201, jpg.text


def test_rejects_wrong_types_and_forged_signatures(client):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)

    exe = _upload(client, headers, expense["id"], "virus.exe", b"MZ\x90\x00", "application/octet-stream")
    assert exe.status_code == 400
    assert "no se acepta" in exe.json()["detail"]

    # Extensión PDF con contenido HTML: la firma no miente.
    forged = _upload(client, headers, expense["id"], "factura.pdf", b"<html>hola</html>", "application/pdf")
    assert forged.status_code == 400
    assert "no corresponde" in forged.json()["detail"]

    fake_png = _upload(client, headers, expense["id"], "ticket.png", PDF, "image/png")
    assert fake_png.status_code == 400

    mismatch = _upload(client, headers, expense["id"], "factura.pdf", PDF, "text/html")
    assert mismatch.status_code == 400

    empty = _upload(client, headers, expense["id"], "vacio.pdf", b"", "application/pdf")
    assert empty.status_code == 400

    assert _list(client, headers, expense["id"]).json()["total"] == 0


def test_rejects_over_10mb_and_the_eleventh(client):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)

    big = PDF + b"0" * storage.MAX_FILE_BYTES
    too_big = _upload(client, headers, expense["id"], "grande.pdf", big, "application/pdf")
    assert too_big.status_code == 400
    assert "10 MB" in too_big.json()["detail"]

    for index in range(storage.MAX_PER_OWNER):
        response = _upload(client, headers, expense["id"], f"f{index}.pdf", PDF + str(index).encode(), "application/pdf")
        assert response.status_code == 201, response.text
    eleventh = _upload(client, headers, expense["id"], "f10.pdf", PDF + b"10", "application/pdf")
    assert eleventh.status_code == 400
    assert "máximo" in eleventh.json()["detail"]


def test_same_file_twice_is_rejected(client):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)
    assert _upload(client, headers, expense["id"], "a.pdf", PDF, "application/pdf").status_code == 201
    again = _upload(client, headers, expense["id"], "b.pdf", PDF, "application/pdf")
    assert again.status_code == 400
    assert "ya está adjunto" in again.json()["detail"]


def test_list_has_no_bytes_and_download_is_identical(client, db):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)
    pdf_id = _upload(client, headers, expense["id"], "factura ñ.pdf", PDF, "application/pdf").json()["id"]
    xml_id = _upload(client, headers, expense["id"], "cfdi.xml", XML, "application/xml").json()["id"]

    listing = _list(client, headers, expense["id"])
    assert listing.status_code == 200
    page = listing.json()
    assert set(page) == {"items", "total", "limit", "offset"}
    assert page["total"] == 2
    assert all("data" not in item for item in page["items"])
    # Los bytes viven en su propia tabla.
    assert db.get(AttachmentBlob, pdf_id) is not None
    assert not hasattr(Attachment, "data")

    pdf = client.get(f"/api/attachments/{pdf_id}/download", headers=headers)
    assert pdf.status_code == 200
    assert pdf.content == PDF
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline;")
    assert "filename*=UTF-8''factura%20%C3%B1.pdf" in pdf.headers["content-disposition"]
    assert pdf.headers["x-content-type-options"] == "nosniff"

    xml = client.get(f"/api/attachments/{xml_id}/download", headers=headers)
    assert xml.content == XML
    assert xml.headers["content-disposition"].startswith("attachment;")


def test_soft_delete_hides_it_but_keeps_the_row(client, db):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)
    attachment_id = _upload(client, headers, expense["id"], "factura.pdf", PDF, "application/pdf").json()["id"]

    deleted = client.delete(f"/api/attachments/{attachment_id}", headers=headers)
    assert deleted.status_code == 204
    assert _list(client, headers, expense["id"]).json()["total"] == 0
    assert client.get(f"/api/attachments/{attachment_id}/download", headers=headers).status_code == 404
    assert client.delete(f"/api/attachments/{attachment_id}", headers=headers).status_code == 404

    row = db.get(Attachment, attachment_id)
    assert row is not None and row.deleted_at is not None and row.deleted_by is not None
    assert db.get(AttachmentBlob, attachment_id) is not None
    # Quitarlo libera el lugar: se puede volver a subir el mismo archivo.
    assert _upload(client, headers, expense["id"], "factura.pdf", PDF, "application/pdf").status_code == 201


def test_closed_month_keeps_its_evidence(client, db):
    headers, org_id, category = _setup(client)
    expense = _expense(client, headers, category, date="2026-09-20")
    attachment_id = _upload(client, headers, expense["id"], "factura.pdf", PDF, "application/pdf").json()["id"]
    db.add(PeriodLock(organization_id=org_id, year=2026, month=9))
    db.commit()

    blocked = client.delete(f"/api/attachments/{attachment_id}", headers=headers)
    assert blocked.status_code == 400
    assert "cerrado" in blocked.json()["detail"]
    assert _list(client, headers, expense["id"]).json()["total"] == 1


def test_tenant_isolation(client):
    headers_a, _org_a, category_a = _setup(client)
    expense = _expense(client, headers_a, category_a)
    attachment_id = _upload(client, headers_a, expense["id"], "factura.pdf", PDF, "application/pdf").json()["id"]

    headers_b, _org_b, _category_b = _setup(client, email="otra@example.com", business="Otra")
    assert _list(client, headers_b, expense["id"]).status_code == 404
    assert _upload(client, headers_b, expense["id"], "x.pdf", PDF, "application/pdf").status_code == 404
    assert client.get(f"/api/attachments/{attachment_id}/download", headers=headers_b).status_code == 404
    assert client.delete(f"/api/attachments/{attachment_id}", headers=headers_b).status_code == 404
    # Sigue intacto para su dueño.
    assert _list(client, headers_a, expense["id"]).json()["total"] == 1


def test_viewer_can_read_but_not_write(client):
    headers, _org, category = _setup(client)
    expense = _expense(client, headers, category)
    attachment_id = _upload(client, headers, expense["id"], "factura.pdf", PDF, "application/pdf").json()["id"]
    created = client.post(
        "/api/organizations/current/members",
        headers=headers,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    assert created.status_code in (200, 201), created.text
    viewer = auth_headers(
        client.post("/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}).json()
    )

    assert _upload(client, viewer, expense["id"], "otro.pdf", PDF + b"x", "application/pdf").status_code == 403
    assert client.delete(f"/api/attachments/{attachment_id}", headers=viewer).status_code == 403
    assert _list(client, viewer, expense["id"]).json()["total"] == 1
    assert client.get(f"/api/attachments/{attachment_id}/download", headers=viewer).status_code == 200


def test_attachments_count_in_expense_list_and_detail(client):
    headers, _org, category = _setup(client)
    with_files = _expense(client, headers, category, description="Con ticket")
    without = _expense(client, headers, category, description="Sin ticket")
    assert with_files["attachments_count"] == 0
    _upload(client, headers, with_files["id"], "ticket.png", PNG, "image/png")
    second = _upload(client, headers, with_files["id"], "factura.pdf", PDF, "application/pdf").json()
    client.delete(f"/api/attachments/{second['id']}", headers=headers)
    _upload(client, headers, with_files["id"], "cfdi.xml", XML, "application/xml")

    items = {item["id"]: item for item in client.get("/api/expenses", headers=headers).json()["items"]}
    assert items[with_files["id"]]["attachments_count"] == 2
    assert items[without["id"]]["attachments_count"] == 0
    detail = client.get(f"/api/expenses/{with_files['id']}", headers=headers).json()
    assert detail["attachments_count"] == 2
