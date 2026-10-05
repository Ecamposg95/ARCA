"""Exportación a CONTPAQi: las pólizas del mes, cuadradas y sólo las de la empresa."""

from datetime import date
from decimal import Decimal

from app.models.accounting import JournalEntry, JournalEntryLine
from app.services.accounting.contpaqi import ENCODING, HEADER_WIDTH, MOVEMENT_WIDTH
from tests.helpers import auth_headers, register

TODAY = date.today()
MONTH = {"year": TODAY.year, "month": TODAY.month}


def _setup(client, email="dueno@example.com", business="Mi Changarro"):
    headers = auth_headers(register(client, email=email, business=business, initial_cash="100000"))
    account = client.get("/api/accounts", headers=headers).json()[0]

    def category(kind: str, name: str) -> str:
        rows = client.get(f"/api/categories?kind={kind}", headers=headers).json()
        return next(c["id"] for c in rows if c["name"] == name)

    return headers, account, category


def _income(client, headers, account, category, description="Venta de mostrador", amount="11600"):
    response = client.post(
        "/api/income",
        headers=headers,
        json={
            "date": TODAY.isoformat(),
            "description": description,
            "amount": amount,
            "tax_rate": "0.16",
            "category_id": category("INCOME", "Ventas"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _expense(client, headers, account, category):
    response = client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": TODAY.isoformat(),
            "description": "Renta del local",
            "amount": "5800",
            "tax_rate": "0.16",
            "category_id": category("EXPENSE", "Renta"),
            "financial_account_id": account["id"],
            "status": "PAID",
        },
    )
    assert response.status_code == 201, response.text


def _export(client, headers, **params):
    return client.get("/api/accounting/contpaqi", headers=headers, params=params or MONTH)


def _vouchers(text: str) -> list[dict]:
    """Parte el archivo en pólizas con sus movimientos, leyendo por posición."""
    vouchers: list[dict] = []
    for line in text.split("\r\n"):
        if not line:
            continue
        if line.startswith("P "):
            assert len(line) == HEADER_WIDTH
            vouchers.append({"kind": line[12:16].strip(), "concept": line[40:140].strip(), "moves": []})
        else:
            assert line.startswith("M ") and len(line) == MOVEMENT_WIDTH
            vouchers[-1]["moves"].append(
                {
                    "account": line[3:33].strip(),
                    "side": line[45],
                    "amount": Decimal(line[47:67].strip()),
                }
            )
    return vouchers


def test_the_file_downloads_with_its_name_and_encoding(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)

    response = _export(client, headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/plain")
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="polizas-contpaqi-{TODAY.year}-{TODAY.month:02d}.txt"'
    )
    assert response.content.decode(ENCODING).endswith("\r\n")


def test_every_voucher_of_the_month_goes_out_balanced(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    _expense(client, headers, account, category)

    vouchers = _vouchers(_export(client, headers).content.decode(ENCODING))
    total = client.get("/api/accounting/journal-entries", headers=headers).json()["total"]
    assert len(vouchers) == total == 3  # saldo inicial + ingreso + gasto
    for voucher in vouchers:
        cargos = sum(m["amount"] for m in voucher["moves"] if m["side"] == "0")
        abonos = sum(m["amount"] for m in voucher["moves"] if m["side"] == "1")
        assert cargos == abonos > 0
    assert sorted(v["kind"] for v in vouchers) == ["1", "2", "3"]


def test_mapped_accounts_use_the_contpaqi_number_and_the_rest_keep_arcas(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    accounts = client.get("/api/accounting/accounts", headers=headers).json()
    ventas = next(a for a in accounts if a["code"] == "4100")
    client.patch(
        f"/api/accounting/accounts/{ventas['id']}", headers=headers, json={"contpaqi_code": "401-01-000"}
    )

    vouchers = _vouchers(_export(client, headers).content.decode(ENCODING))
    used = {m["account"] for v in vouchers for m in v["moves"]}
    assert "40101000" in used and "4100" not in used
    assert "1100" in used  # sin equivalente: sale con el código de ARCA

    preview = client.get("/api/accounting/contpaqi/preview", headers=headers, params=MONTH).json()
    assert preview["entries"] == len(vouchers)
    assert preview["movements"] == sum(len(v["moves"]) for v in vouchers)
    unmapped = {a["code"] for a in preview["unmapped_accounts"]}
    assert "1100" in unmapped and "4100" not in unmapped


def test_accents_survive_and_unsupported_characters_do_not_break_the_file(client):
    headers, account, category = _setup(client)
    _income(client, headers, account, category, description="Café para el señor Ñandú ✓")

    raw = _export(client, headers).content
    assert "Café para el señor Ñandú ?".encode(ENCODING) in raw


def test_only_the_active_company_goes_out(client):
    mine, my_account, my_category = _setup(client, email="yo@example.com", business="Mía")
    theirs, their_account, their_category = _setup(client, email="otro@example.com", business="Ajena")
    _income(client, mine, my_account, my_category, description="Venta mía")
    _income(client, theirs, their_account, their_category, description="Venta ajena")

    text = _export(client, mine).content.decode(ENCODING)
    assert "Venta mía" in text and "Venta ajena" not in text


def test_a_month_without_vouchers_is_a_404(client):
    headers, _account, _category = _setup(client)
    response = _export(client, headers, year=2001, month=1)
    assert response.status_code == 404
    assert response.json()["detail"] == "No hay pólizas en ese mes."

    preview = client.get(
        "/api/accounting/contpaqi/preview", headers=headers, params={"year": 2001, "month": 1}
    ).json()
    assert (preview["entries"], preview["movements"], preview["unmapped_accounts"]) == (0, 0, [])


def test_an_unbalanced_voucher_blocks_the_whole_file(client, db):
    headers, account, category = _setup(client)
    _income(client, headers, account, category)
    # Se descuadra una póliza a mano: el motor no lo permite, pero el export no confía.
    entry = db.query(JournalEntry).filter(JournalEntry.kind == "INGRESO").one()
    line = (
        db.query(JournalEntryLine)
        .filter(JournalEntryLine.journal_entry_id == entry.id, JournalEntryLine.debit > 0)
        .first()
    )
    line.debit = line.debit + 1
    db.flush()

    response = _export(client, headers)
    assert response.status_code == 409
    assert entry.folio in response.json()["detail"]


def test_a_viewer_cannot_export(client):
    owner, _account, _category = _setup(client)
    client.post(
        "/api/organizations/current/members",
        headers=owner,
        json={"email": "mira@example.com", "name": "Mira", "role": "VIEWER", "password": "supersegura123"},
    )
    viewer = auth_headers(
        client.post(
            "/api/auth/login", json={"email": "mira@example.com", "password": "supersegura123"}
        ).json()
    )
    assert _export(client, viewer).status_code == 403
