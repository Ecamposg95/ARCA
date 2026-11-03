"""PostgreSQL no admite FOR UPDATE sobre el lado nullable de un LEFT JOIN.

Las cuentas y las pólizas cargan su unidad con lazy="joined"; SQLite ignora
FOR UPDATE, así que se compila contra el dialecto de PostgreSQL.
"""

from sqlalchemy.dialects import postgresql

from app.models.financial_account import FinancialAccount
from app.models.accounting import JournalEntry


def _sql(query) -> str:
    return str(query.statement.compile(dialect=postgresql.dialect()))


def test_cuenta_bloqueada_solo_su_tabla(db):
    query = db.query(FinancialAccount).with_for_update(of=FinancialAccount)
    sql = _sql(query)
    assert "LEFT OUTER JOIN" in sql
    assert "FOR UPDATE OF financial_accounts" in sql


def test_get_locked_account_usa_of(monkeypatch, db):
    from app.services import transactions

    seen = {}
    original = type(db.query(FinancialAccount)).with_for_update

    def spy(self, *args, **kwargs):
        seen.update(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(db.query(FinancialAccount)), "with_for_update", spy)
    try:
        transactions.get_locked_account(db, "org", "nope")
    except ValueError:
        pass
    assert seen.get("of") is FinancialAccount


def test_poliza_bloqueada_solo_su_tabla(db):
    sql = _sql(db.query(JournalEntry).with_for_update(of=JournalEntry))
    assert "FOR UPDATE OF journal_entries" in sql
