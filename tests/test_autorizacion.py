"""Autorización por monto (spec 2026-11-02): lo que alcanza el umbral no se
registra, espera en la bandeja a quien tiene facultad de autorizar."""

from datetime import date, timedelta
from decimal import Decimal

from tests.helpers import auth_headers, register

THRESHOLD = "100000"


def _company(client, threshold=THRESHOLD, member_limit=None, initial_cash="500000"):
    body = register(client, initial_cash=initial_cash)
    headers = auth_headers(body)
    config = {"approval_threshold": threshold, "member_capture_limit": member_limit}
    response = client.patch("/api/organizations/current/approvals", headers=headers, json=config)
    assert response.status_code == 200, response.text
    account = client.get("/api/accounts", headers=headers).json()[0]
    categories = client.get("/api/categories?kind=EXPENSE", headers=headers).json()
    renta = next(c for c in categories if c["name"] == "Renta")
    return body, headers, account, renta


def _teammate(client, owner_headers, email, role, can_authorize=False):
    invited = client.post(
        "/api/organizations/current/members",
        headers=owner_headers,
        json={"email": email, "name": email.split("@")[0].title(), "role": role, "password": "supersegura123"},
    )
    assert invited.status_code == 201, invited.text
    if can_authorize:
        patched = client.patch(
            f"/api/organizations/current/members/{invited.json()['id']}",
            headers=owner_headers,
            json={"can_authorize": True},
        )
        assert patched.status_code == 200, patched.text
    login = client.post("/api/auth/login", json={"email": email, "password": "supersegura123"}).json()
    return login, auth_headers(login)


def _expense(client, headers, account, renta, amount, status="PAID", when="2026-08-05", vendor_id=None):
    return client.post(
        "/api/expenses",
        headers=headers,
        json={
            "date": when,
            "description": "Renta de agosto",
            "amount": amount,
            "category_id": renta["id"],
            "financial_account_id": account["id"],
            "status": status,
            "vendor_id": vendor_id,
        },
    )


def _balance(client, headers, account):
    return client.get(f"/api/accounts/{account['id']}", headers=headers).json()["current_balance"]


def _pending(client, headers, source=None):
    url = "/api/proposals?status=PROPOSED" + (f"&source={source}" if source else "")
    return client.get(url, headers=headers).json()


# --- Gastos ---------------------------------------------------------------


def test_expense_below_threshold_is_registered(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    response = _expense(client, admin, account, renta, "99999.99")
    assert response.status_code == 201, response.text
    assert _balance(client, admin, account) == "400000.01"


def test_expense_at_threshold_goes_to_inbox_without_touching_balances(client):
    _, owner, account, renta = _company(client)
    vendor = client.post("/api/vendors", headers=owner, json={"name": "Adrián Estrada"}).json()
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")

    response = _expense(client, admin, account, renta, THRESHOLD, vendor_id=vendor["id"])
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["pending_approval"] is True
    assert body["proposal_id"]
    assert body["detail"] == "Se envió a autorización: supera el umbral de $100,000.00."
    assert body["authorizers"] == ["Dueño"]

    # No existe para nadie: ni gasto, ni movimiento, ni saldo.
    assert client.get("/api/expenses", headers=owner).json()["total"] == 0
    assert client.get("/api/transactions", headers=owner).json()["total"] == 0
    assert _balance(client, owner, account) == "500000.00"

    inbox = _pending(client, owner, source="approval")
    assert inbox["total"] == 1
    item = inbox["items"][0]
    assert item["kind"] == "EXPENSE"
    assert item["source"] == "approval"
    assert item["requested_by_name"] == "Abraham"
    assert item["summary"] == "Gasto de $100,000.00 a Adrián Estrada · Renta de agosto"
    assert "Abraham" in item["evidence"]


def test_owner_and_authorizer_register_directly_and_are_audited(client, db):
    from app.models.agent import AgentActionLog

    _, owner, account, renta = _company(client)
    _, liza = _teammate(client, owner, "liza@lafe.mx", "ADMIN", can_authorize=True)

    assert _expense(client, owner, account, renta, "150000").status_code == 201
    assert _expense(client, liza, account, renta, "120000").status_code == 201
    assert _balance(client, owner, account) == "230000.00"
    assert _pending(client, owner)["total"] == 0

    audited = db.query(AgentActionLog).filter(AgentActionLog.tool == "self_authorized_expense").all()
    assert len(audited) == 2
    assert {row.arguments["amount"] for row in audited} == {"150000", "120000"}


def test_member_above_capture_limit_gets_403_before_the_threshold(client):
    _, owner, account, renta = _company(client, member_limit="2000")
    _, auxiliar = _teammate(client, owner, "aux@lafe.mx", "MEMBER")

    too_big = _expense(client, auxiliar, account, renta, "150000")
    assert too_big.status_code == 403
    assert too_big.json()["detail"] == "Ese monto necesita a un administrador."
    assert _pending(client, owner)["total"] == 0  # ni siquiera llegó a la bandeja

    above_limit = _expense(client, auxiliar, account, renta, "2000.01")
    assert above_limit.status_code == 403

    assert _expense(client, auxiliar, account, renta, "2000").status_code == 201


def test_approve_executes_with_the_requester_as_author(client, db):
    from app.models.expense import Expense

    owner_body, owner, account, renta = _company(client)
    admin_body, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    proposal_id = _expense(client, admin, account, renta, "120000").json()["proposal_id"]

    approved = client.post(f"/api/proposals/{proposal_id}/approve", headers=owner)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    expense = db.get(Expense, approved.json()["result_id"])
    assert expense.status == "PAID"
    assert expense.created_by == admin_body["user"]["id"]
    assert _balance(client, owner, account) == "380000.00"

    from app.models.agent import AgentProposal

    proposal = db.get(AgentProposal, proposal_id)
    assert proposal.reviewed_by == owner_body["user"]["id"]
    assert proposal.requested_by == admin_body["user"]["id"]

    trial = client.get("/api/accounting/trial-balance", headers=owner).json()
    assert Decimal(str(trial["total_debit"])) == Decimal(str(trial["total_credit"]))


def test_reject_requires_a_reason_and_changes_nothing(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    proposal_id = _expense(client, admin, account, renta, "120000").json()["proposal_id"]

    without = client.post(f"/api/proposals/{proposal_id}/reject", headers=owner, json={})
    assert without.status_code == 400
    assert "motivo" in without.json()["detail"]

    rejected = client.post(
        f"/api/proposals/{proposal_id}/reject", headers=owner, json={"reason": "No era el momento"}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert client.get("/api/expenses", headers=owner).json()["total"] == 0
    assert _balance(client, owner, account) == "500000.00"


def test_approving_or_rejecting_without_faculty_is_403(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    _, other = _teammate(client, owner, "otro@lafe.mx", "ADMIN")
    proposal_id = _expense(client, admin, account, renta, "120000").json()["proposal_id"]

    for headers in (admin, other):
        denied = client.post(f"/api/proposals/{proposal_id}/approve", headers=headers)
        assert denied.status_code == 403
        assert denied.json()["detail"] == "Solo quien autoriza puede aprobar."
        denied = client.post(
            f"/api/proposals/{proposal_id}/reject", headers=headers, json={"reason": "no"}
        )
        assert denied.status_code == 403
    assert _pending(client, owner)["total"] == 1


def test_pending_expense_is_evaluated_when_paid_not_when_created(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")

    created = _expense(client, admin, account, renta, "150000", status="PENDING")
    assert created.status_code == 201, created.text
    expense_id = created.json()["id"]
    assert _pending(client, owner)["total"] == 0

    paying = client.post(f"/api/expenses/{expense_id}/pay", headers=admin, json={})
    assert paying.status_code == 202, paying.text
    assert client.get(f"/api/expenses/{expense_id}", headers=owner).json()["status"] == "PENDING"
    assert _balance(client, owner, account) == "500000.00"

    inbox = _pending(client, owner, source="approval")
    assert inbox["items"][0]["kind"] == "EXPENSE_PAYMENT"
    approved = client.post(f"/api/proposals/{paying.json()['proposal_id']}/approve", headers=owner)
    assert approved.status_code == 200, approved.text
    assert client.get(f"/api/expenses/{expense_id}", headers=owner).json()["status"] == "PAID"
    assert _balance(client, owner, account) == "350000.00"


def test_closed_month_on_approve_keeps_the_proposal_alive(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    end = date.today().replace(day=1) - timedelta(days=1)
    proposal_id = _expense(client, admin, account, renta, "120000", when=end.isoformat()).json()[
        "proposal_id"
    ]
    closed = client.post(
        "/api/periods/close", headers=owner, json={"year": end.year, "month": end.month}
    )
    assert closed.status_code in (200, 201), closed.text

    approved = client.post(f"/api/proposals/{proposal_id}/approve", headers=owner)
    assert approved.status_code == 400
    assert "cerrado" in approved.json()["detail"]
    assert _pending(client, owner)["total"] == 1
    assert _balance(client, owner, account) == "500000.00"
    assert client.get("/api/expenses", headers=owner).json()["total"] == 0


# --- Cuentas por pagar y traspasos ------------------------------------------


def test_partial_payable_payment_above_threshold_goes_to_inbox(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    vendor = client.post("/api/vendors", headers=owner, json={"name": "Reactivos del Norte"}).json()
    payable = client.post(
        "/api/payables",
        headers=admin,
        json={
            "vendor_id": vendor["id"],
            "description": "Reactivos",
            "amount": "300000",
            "due_date": "2026-09-30",
            "category_id": renta["id"],
        },
    ).json()

    small = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=admin,
        json={"amount": "50000", "financial_account_id": account["id"]},
    )
    assert small.status_code == 200, small.text

    big = client.post(
        f"/api/payables/{payable['id']}/pay",
        headers=admin,
        json={"amount": "150000", "financial_account_id": account["id"]},
    )
    assert big.status_code == 202, big.text
    assert client.get(f"/api/payables/{payable['id']}", headers=owner).json()["amount_paid"] == "50000.00"
    assert _balance(client, owner, account) == "450000.00"

    item = _pending(client, owner, source="approval")["items"][0]
    assert item["kind"] == "PAYABLE_PAYMENT"
    assert item["summary"] == "Pago de $150,000.00 a Reactivos del Norte · Reactivos"

    approved = client.post(f"/api/proposals/{big.json()['proposal_id']}/approve", headers=owner)
    assert approved.status_code == 200, approved.text
    refreshed = client.get(f"/api/payables/{payable['id']}", headers=owner).json()
    assert refreshed["amount_paid"] == "200000.00" and refreshed["status"] == "PARTIAL"
    assert _balance(client, owner, account) == "300000.00"


def test_transfer_above_threshold_goes_to_inbox(client):
    _, owner, cash, _ = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    bank = client.post(
        "/api/accounts", headers=owner, json={"name": "BBVA", "type": "BANK", "initial_balance": "0"}
    ).json()

    response = client.post(
        "/api/transactions/transfer",
        headers=admin,
        json={
            "from_account_id": cash["id"],
            "to_account_id": bank["id"],
            "amount": "250000",
            "date": "2026-08-10",
        },
    )
    assert response.status_code == 202, response.text
    assert _balance(client, owner, cash) == "500000.00"
    assert _balance(client, owner, bank) == "0.00"
    item = _pending(client, owner, source="approval")["items"][0]
    assert item["kind"] == "TRANSFER"
    assert item["summary"] == "Traspaso de $250,000.00 de Caja a BBVA"

    approved = client.post(f"/api/proposals/{response.json()['proposal_id']}/approve", headers=owner)
    assert approved.status_code == 200, approved.text
    assert _balance(client, owner, cash) == "250000.00"
    assert _balance(client, owner, bank) == "250000.00"
    assert client.get("/api/transactions?transaction_type=TRANSFER_IN", headers=owner).json()["total"] == 1


def test_transfer_below_threshold_still_works_directly(client):
    _, owner, cash, _ = _company(client)
    bank = client.post(
        "/api/accounts", headers=owner, json={"name": "BBVA", "type": "BANK", "initial_balance": "0"}
    ).json()
    response = client.post(
        "/api/transactions/transfer",
        headers=owner,
        json={"from_account_id": cash["id"], "to_account_id": bank["id"], "amount": "100", "date": "2026-08-10"},
    )
    assert response.status_code == 201, response.text
    assert len(response.json()) == 2


# --- Bandeja, aislamiento y configuración -----------------------------------


def test_a_proposal_from_another_company_is_404(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    proposal_id = _expense(client, admin, account, renta, "120000").json()["proposal_id"]

    other = auth_headers(register(client, email="ajena@example.com", business="Otra"))
    assert client.post(f"/api/proposals/{proposal_id}/approve", headers=other).status_code == 404
    assert client.get("/api/proposals", headers=other).json()["total"] == 0


def test_source_filter_and_badge_count_include_approvals(client):
    _, owner, account, renta = _company(client)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    _expense(client, admin, account, renta, "120000")

    key = client.post("/api/agent-keys", headers=owner, json={"name": "Bot", "scopes": "READ,PROPOSE"}).json()
    proposed = client.post(
        "/api/agent/invoke",
        headers={"Authorization": f"Bearer {key['token']}"},
        json={
            "tool": "propose_expense",
            "arguments": {
                "date": "2026-08-24",
                "description": "Cargo del bot",
                "amount": "999",
                "category_id": renta["id"],
                "summary": "Cargo no identificado",
            },
        },
    )
    assert proposed.status_code == 200, proposed.text

    assert _pending(client, owner)["total"] == 2
    assert _pending(client, owner, source="approval")["total"] == 1
    assert _pending(client, owner, source="agent")["total"] == 1
    assert _pending(client, owner, source="assistant")["total"] == 0
    assert _pending(client, owner, source="system")["total"] == 0
    count = client.get("/api/proposals/pending-count", headers=owner).json()
    assert count == {"count": 2, "approval": 1}


def test_member_cannot_see_or_edit_the_approval_settings(client):
    _, owner, _, _ = _company(client)
    _, auxiliar = _teammate(client, owner, "aux@lafe.mx", "MEMBER")
    assert client.get("/api/organizations/current/approvals", headers=auxiliar).status_code == 403
    denied = client.patch(
        "/api/organizations/current/approvals", headers=auxiliar, json={"approval_threshold": None}
    )
    assert denied.status_code == 403

    config = client.get("/api/organizations/current/approvals", headers=owner).json()
    assert config == {"approval_threshold": "100000.00", "member_capture_limit": None}


def test_no_threshold_means_nothing_waits(client):
    _, owner, account, renta = _company(client, threshold=None)
    _, admin = _teammate(client, owner, "abraham@lafe.mx", "ADMIN")
    assert _expense(client, admin, account, renta, "400000").status_code == 201


def test_me_exposes_can_authorize_and_the_owner_keeps_it(client):
    owner_body, owner, _, _ = _company(client)
    liza_body, liza = _teammate(client, owner, "liza@lafe.mx", "ADMIN", can_authorize=True)

    me = client.get("/api/me", headers=liza).json()
    assert me["memberships"][0]["can_authorize"] is True
    me = client.get("/api/me", headers=owner).json()
    assert me["memberships"][0]["can_authorize"] is True  # el dueño siempre

    members = client.get("/api/organizations/current/members", headers=owner).json()["items"]
    by_role = {m["role"]: m for m in members}
    assert by_role["OWNER"]["can_authorize"] is True
    assert by_role["ADMIN"]["can_authorize"] is True
    denied = client.patch(
        f"/api/organizations/current/members/{by_role['OWNER']['id']}",
        headers=liza,
        json={"can_authorize": False},
    )
    assert denied.status_code == 400

    # Quitar la facultad la quita de verdad; la invitación queda igual.
    revoked = client.patch(
        f"/api/organizations/current/members/{by_role['ADMIN']['id']}",
        headers=owner,
        json={"can_authorize": False},
    )
    assert revoked.status_code == 200 and revoked.json()["can_authorize"] is False
    assert revoked.json()["role"] == "ADMIN"
