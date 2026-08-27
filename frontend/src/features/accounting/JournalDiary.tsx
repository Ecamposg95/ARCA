/** Libro diario maestro-detalle: la lista a la izquierda, la póliza a la derecha.
 *
 *  Sin modal: un contador revisa pólizas en serie, y abrir-cerrar-abrir es
 *  fricción pura. La selección vive en la URL (?poliza=) para poder compartir
 *  "mira esta póliza" con un enlace. En pantallas angostas el detalle entra
 *  como panel deslizante y la lista nunca pierde su scroll.
 */

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { TableFooter } from '@/components/ui/Pagination'
import { formatDate, formatMoney } from '@/lib/format'
import type { JournalEntry, Page } from '@/types/api'

const SOURCE_LABELS: Record<string, string> = {
  income: 'Ingreso',
  expense: 'Gasto',
  receivable: 'Cuenta por cobrar',
  payable: 'Cuenta por pagar',
  transfer: 'Traspaso',
  financial_account: 'Saldo inicial',
  fixed_asset: 'Activo fijo',
  depreciation: 'Depreciación',
  loan: 'Préstamo',
  loan_payment: 'Pago de préstamo',
}

function EntryDetail({
  entry,
  accountLabel,
  onClose,
}: {
  entry: JournalEntry
  accountLabel: (id: string) => string
  onClose?: () => void
}) {
  const total = entry.lines.reduce((sum, line) => sum + Number(line.debit), 0)
  return (
    <div className="flex h-full flex-col rounded-xl border border-border bg-surface shadow-card">
      <div className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <div className="figures text-sm font-semibold">{entry.folio}</div>
          <p className="mt-0.5 text-sm">{entry.description}</p>
          <p className="mt-1 text-xs text-muted">
            {formatDate(entry.date)}
            {entry.source_type
              ? ` · ${SOURCE_LABELS[entry.source_type] ?? entry.source_type}`
              : ''}
          </p>
        </div>
        {onClose ? (
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar detalle"
            className="rounded-lg p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-ink lg:hidden"
          >
            ✕
          </button>
        ) : null}
      </div>
      <div className="flex-1 overflow-y-auto px-5 py-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-muted">
              <th className="pb-1.5 text-left font-semibold">Cuenta</th>
              <th className="pb-1.5 text-right font-semibold">Cargo</th>
              <th className="pb-1.5 text-right font-semibold">Abono</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {entry.lines.map((line) => (
              <tr key={line.id}>
                <td className="py-2">
                  {accountLabel(line.account_id)}
                  {line.description ? (
                    <span className="block text-xs text-muted">{line.description}</span>
                  ) : null}
                </td>
                <td className="figures whitespace-nowrap py-2 pl-3 text-right align-top">
                  {Number(line.debit) > 0 ? formatMoney(line.debit) : '—'}
                </td>
                <td className="figures whitespace-nowrap py-2 pl-3 text-right align-top">
                  {Number(line.credit) > 0 ? formatMoney(line.credit) : '—'}
                </td>
              </tr>
            ))}
            <tr className="border-t-2 border-ink/70 font-semibold">
              <td className="py-2">
                Cuadra
                <span className="ml-2 text-xs font-medium text-pos">cargos = abonos ✓</span>
              </td>
              <td className="figures whitespace-nowrap py-2 pl-3 text-right">{formatMoney(total)}</td>
              <td className="figures whitespace-nowrap py-2 pl-3 text-right">{formatMoney(total)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function JournalDiary({
  page,
  onOffsetChange,
  accountLabel,
}: {
  page: Page<JournalEntry>
  onOffsetChange: (offset: number) => void
  accountLabel: (id: string) => string
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const listRef = useRef<HTMLDivElement>(null)
  // En angosto el panel sólo se abre por clic: autoseleccionar la primera
  // póliza no debe taparle la lista a nadie.
  const [drawerOpen, setDrawerOpen] = useState(false)

  const entries = page.items
  const requested = searchParams.get('poliza')
  const selected = entries.find((entry) => entry.id === requested) ?? entries[0] ?? null

  function select(entry: JournalEntry, fromClick = false) {
    const params = new URLSearchParams(searchParams)
    params.set('poliza', entry.id)
    setSearchParams(params, { replace: true })
    if (fromClick) setDrawerOpen(true)
  }

  // ↑↓ recorre pólizas cuando el foco está en la lista; la fila activa
  // permanece visible sin que la página entera brinque.
  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    if (!selected) return
    const index = entries.findIndex((entry) => entry.id === selected.id)
    const next = entries[index + (event.key === 'ArrowDown' ? 1 : -1)]
    if (next) select(next)
  }

  useEffect(() => {
    if (!selected) return
    listRef.current
      ?.querySelector(`[data-entry="${selected.id}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [selected])

  return (
    <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_400px] lg:items-start lg:gap-4">
      <div
        ref={listRef}
        tabIndex={0}
        onKeyDown={onKeyDown}
        aria-label="Pólizas del periodo (↑↓ para navegar)"
        className="overflow-hidden rounded-xl border border-border bg-surface shadow-card outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <div className="max-h-[70vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-4 py-2.5 font-semibold">Folio</th>
                <th className="px-4 py-2.5 font-semibold">Fecha</th>
                <th className="px-4 py-2.5 font-semibold">Concepto</th>
                <th className="px-4 py-2.5 text-right font-semibold">Importe</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {entries.map((entry) => {
                const active = selected?.id === entry.id
                const total = entry.lines.reduce((sum, line) => sum + Number(line.debit), 0)
                return (
                  <tr
                    key={entry.id}
                    data-entry={entry.id}
                    onClick={() => select(entry, true)}
                    aria-selected={active}
                    className={`cursor-pointer border-l-2 ${
                      active
                        ? 'border-l-accent bg-accent-soft/60'
                        : 'border-l-transparent hover:bg-surface-2/50'
                    }`}
                  >
                    <td className="figures whitespace-nowrap px-4 py-2.5 text-xs text-muted">
                      {entry.folio}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                      {formatDate(entry.date)}
                    </td>
                    <td className="max-w-[26ch] truncate px-4 py-2.5 font-medium">
                      {entry.description}
                    </td>
                    <td className="figures whitespace-nowrap px-4 py-2.5 text-right">
                      {formatMoney(total)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        <TableFooter page={page} onOffsetChange={onOffsetChange} noun="pólizas" />
      </div>

      {/* Escritorio: el detalle acompaña a la lista, pegado arriba. */}
      {selected ? (
        <div className="hidden lg:sticky lg:top-4 lg:block lg:max-h-[78vh]">
          <EntryDetail entry={selected} accountLabel={accountLabel} />
        </div>
      ) : null}

      {/* Angosto: panel deslizante sobre la lista, sólo tras un clic. */}
      {selected && drawerOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/45"
            onClick={() => setDrawerOpen(false)}
            aria-hidden
          />
          <div className="absolute inset-y-0 right-0 w-full max-w-md p-2">
            <EntryDetail
              entry={selected}
              accountLabel={accountLabel}
              onClose={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
