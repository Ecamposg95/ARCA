/** Herramientas de tabla profesional: orden por columna, selección múltiple y
 *  acciones en lote. Compartidas por las cuatro listas grandes para que todas
 *  se comporten igual. */

import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Button } from '@/components/ui/Button'

/* ---------- Orden por columna ---------- */

/** Encabezado clicable. `sort` es el valor crudo del querystring ("-amount"). */
export function SortableHeader({
  field,
  label,
  sort,
  onSort,
  align = 'left',
}: {
  field: string
  label: string
  sort: string
  onSort: (next: string) => void
  align?: 'left' | 'right'
}) {
  const active = sort === field || sort === `-${field}`
  const descending = sort === `-${field}`
  return (
    <button
      type="button"
      onClick={() => {
        // Ciclo: sin orden → descendente (lo más común: lo grande primero) →
        // ascendente → sin orden.
        if (!active) onSort(`-${field}`)
        else if (descending) onSort(field)
        else onSort('')
      }}
      className={`inline-flex items-center gap-1 uppercase tracking-wider transition-colors hover:text-ink ${
        active ? 'text-ink' : ''
      } ${align === 'right' ? 'justify-end text-right' : ''}`}
      title={`Ordenar por ${label.toLowerCase()}`}
    >
      {label}
      <span className={`text-[9px] ${active ? 'opacity-100' : 'opacity-0'}`} aria-hidden>
        {descending ? '▼' : '▲'}
      </span>
    </button>
  )
}

/* ---------- Selección múltiple ---------- */

export function useRowSelection<T extends { id: string }>(items: T[]) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())

  const toggle = useCallback((id: string) => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const pageIds = useMemo(() => items.map((item) => item.id), [items])
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => selected.has(id))

  const togglePage = useCallback(() => {
    setSelected((previous) => {
      const next = new Set(previous)
      if (pageIds.every((id) => next.has(id))) pageIds.forEach((id) => next.delete(id))
      else pageIds.forEach((id) => next.add(id))
      return next
    })
  }, [pageIds])

  const clear = useCallback(() => setSelected(new Set()), [])

  const selectedItems = useMemo(
    () => items.filter((item) => selected.has(item.id)),
    [items, selected],
  )

  return { selected, selectedItems, toggle, togglePage, allOnPage, clear }
}

export function RowCheckbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: () => void
  label: string
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      onChange={onChange}
      aria-label={label}
      // Detener la propagación: marcar una fila no debe disparar el clic de la fila.
      onClick={(event) => event.stopPropagation()}
      className="h-4 w-4 cursor-pointer rounded border-border accent-[hsl(var(--accent))]"
    />
  )
}

/* ---------- Barra de acciones en lote ---------- */

export function BatchBar({
  count,
  onClear,
  children,
}: {
  count: number
  onClear: () => void
  children: ReactNode
}) {
  if (count === 0) return null
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-accent/40 bg-accent-soft px-4 py-2.5">
      <span className="figures text-sm font-semibold">{count}</span>
      <span className="text-sm">seleccionada{count === 1 ? '' : 's'}</span>
      <div className="mx-1 h-4 w-px bg-border-strong" aria-hidden />
      {children}
      <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={onClear}>
        Quitar selección
      </Button>
    </div>
  )
}

/* ---------- Lotes que sobreviven a errores parciales ---------- */

export interface BatchFailure {
  label: string
  error: string
}

export interface BatchOutcome {
  ok: number
  failures: BatchFailure[]
}

/** Ejecuta una acción por elemento EN SECUENCIA y nunca se traga un error:
 *  devuelve cuántas aplicaron y cuáles fallaron con su motivo. Secuencial a
 *  propósito: los pagos mutan saldos y dispararlos en paralelo invita a
 *  condiciones de carrera en el lock de la cuenta. */
export async function runBatch<T>(
  items: T[],
  label: (item: T) => string,
  action: (item: T) => Promise<void>,
  extractError: (error: unknown) => string,
): Promise<BatchOutcome> {
  const outcome: BatchOutcome = { ok: 0, failures: [] }
  for (const item of items) {
    try {
      await action(item)
      outcome.ok += 1
    } catch (error) {
      outcome.failures.push({ label: label(item), error: extractError(error) })
    }
  }
  return outcome
}

export function BatchNotice({
  outcome,
  noun,
  onClose,
}: {
  outcome: BatchOutcome | null
  noun: string
  onClose: () => void
}) {
  if (!outcome) return null
  const failed = outcome.failures.length
  return (
    <div
      className={`mb-3 rounded-xl border px-4 py-3 text-sm ${
        failed ? 'border-warn/40 bg-warn/10' : 'border-pos/40 bg-pos/10'
      }`}
    >
      <p>
        <span className="figures font-semibold">{outcome.ok}</span> {noun}
        {failed ? (
          <>
            {' · '}
            <span className="figures font-semibold">{failed}</span> con error:
          </>
        ) : null}
      </p>
      {failed ? (
        <ul className="mt-1 list-disc pl-5 text-xs">
          {outcome.failures.map((failure, index) => (
            <li key={index}>
              <span className="font-medium">{failure.label}</span> — {failure.error}
            </li>
          ))}
        </ul>
      ) : null}
      <button type="button" className="mt-1 text-xs text-muted underline" onClick={onClose}>
        Cerrar
      </button>
    </div>
  )
}

/* ---------- Exportar selección a CSV ---------- */

/** CSV con BOM (mismo criterio que la exportación de reportes: sin él, Excel
 *  en Windows destroza los acentos) generado en el cliente y descargado. */
export function exportRowsCsv(filename: string, headers: string[], rows: string[][]) {
  const escape = (cell: string) =>
    /[",\n]/.test(cell) ? `"${cell.replace(/"/g, '""')}"` : cell
  const lines = [headers, ...rows].map((row) => row.map(escape).join(','))
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

/* ---------- Filtros con contador ---------- */

export function FilterToggle({
  count,
  open,
  onToggle,
}: {
  count: number
  open: boolean
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
        count > 0
          ? 'bg-accent text-on-accent'
          : 'border border-border bg-surface text-muted hover:text-ink'
      }`}
    >
      Filtros{count > 0 ? ` (${count})` : ''} {open ? '▴' : '▾'}
    </button>
  )
}

export function FilterChip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">
      {label}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Quitar filtro ${label}`}
        className="text-muted hover:text-ink"
      >
        ×
      </button>
    </span>
  )
}
