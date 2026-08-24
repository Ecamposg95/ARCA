# ADR-003 — Ledger de partida doble con motor centralizado

**Fecha:** 2026-08-24 · **Estado:** aceptada

## Contexto

Task pack §16–18: ledger correcto sin complejidad prematura, y reglas contables centralizadas. El riesgo clásico es que cada endpoint arme sus asientos y el invariante se erosione.

## Decisión

- Tablas `accounts` (catálogo por organización, seed §17), `journal_entries`, `journal_entry_lines`.
- ÚNICO punto de escritura: `post_journal_entry()` (engine.py) — valida ≥2 líneas, cargo XOR abono por línea, `SUM(debit) == SUM(credit)` en `Decimal`, cuentas del tenant.
- Reglas de negocio → asiento en `rules.py`, una función por evento (income_paid, expense_paid, opening_balance, transfer...).
- Separación de conceptos: Operación de negocio (Income/Expense) → Movimiento (FinancialTransaction, muta saldo con lock) → Póliza (ledger). `source_type`/`source_id` enlazan las capas.
- Reportes (P&L, Balance, Balanza) SIEMPRE calculados del ledger.
- Cancelaciones: estado `CANCELLED`; una operación contabilizada no se borra — los reversos serán pólizas de reversa (fase posterior).

## Consecuencias

- El invariante vive en un archivo y sus tests; imposible de romper desde routers.
- Assets = Liabilities + Equity se cumple por construcción (test en `tests/test_reports.py`).
