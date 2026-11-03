/** Historial de cambios de un registro (HU-09): quién, cuándo, qué y cuál era el valor anterior.
 *
 *  El backend ya manda etiquetas en español y los nombres de las referencias
 *  (categoría, cuenta, proveedor…); aquí sólo se da formato.
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { formatMoney } from '@/lib/format'
import type { HistoryAction, HistoryEvent, HistoryFieldChange, Page } from '@/types/api'

export const ACTION_LABELS: Record<HistoryAction, string> = {
  CREATE: 'Registró',
  UPDATE: 'Editó',
  CANCEL: 'Canceló',
  PAY: 'Registró un pago',
  APPROVE: 'Autorizó',
  REJECT: 'Rechazó',
  DELETE: 'Eliminó',
}

const ACTION_DOT: Record<HistoryAction, string> = {
  CREATE: 'bg-accent',
  UPDATE: 'bg-warn',
  CANCEL: 'bg-neg',
  PAY: 'bg-pos',
  APPROVE: 'bg-pos',
  REJECT: 'bg-neg',
  DELETE: 'bg-neg',
}

export const SOURCE_LABELS: Record<HistoryEvent['source'], string> = {
  web: 'ONE Finance',
  assistant: 'asistente',
  agent: 'agente',
  import: 'importación',
  approval: 'autorización',
  system: 'sistema',
}

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pendiente',
  PAID: 'Pagado',
  CANCELLED: 'Cancelado',
  OPEN: 'Abierta',
  PARTIAL: 'Parcial',
  PROPOSED: 'Por revisar',
  APPROVED: 'Autorizada',
  REJECTED: 'Rechazada',
}

const PAYMENT_LABELS: Record<string, string> = {
  EFECTIVO: 'Efectivo',
  TRANSFERENCIA: 'Transferencia',
  TARJETA_DEBITO: 'Tarjeta de débito',
  TARJETA_CREDITO: 'Tarjeta de crédito',
}

function formatDay(iso: string): string {
  const [year, month, day] = iso.split('T')[0].split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString('es-MX', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })
}

/** "3 de noviembre de 2026, 14:05" */
export function formatWhen(iso: string): string {
  // El backend manda UTC; sin zona explícita el navegador lo leería como local.
  const normalized = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`
  return new Date(normalized).toLocaleString('es-MX', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatValue(change: HistoryFieldChange, side: 'old' | 'new'): string {
  const value = change[side]
  const display = side === 'old' ? change.old_display : change.new_display
  if (value === null || value === undefined || value === '') return '—'
  if (display) return display
  switch (change.kind) {
    case 'money':
      return formatMoney(String(value))
    case 'date':
      return formatDay(String(value))
    case 'status':
      return STATUS_LABELS[String(value)] ?? String(value)
    case 'bool':
      return value === true || value === 'true' ? 'Sí' : 'No'
    case 'rate':
      return `${(Number(value) * 100).toLocaleString('es-MX', { maximumFractionDigits: 2 })}%`
    case 'ref':
      return 'Registro no disponible'
    default:
      if (change.field === 'payment_method') return PAYMENT_LABELS[String(value)] ?? String(value)
      return String(value)
  }
}

export function ChangeList({ event }: { event: HistoryEvent }) {
  if (event.changes.length === 0) return null
  const creating = event.action === 'CREATE'
  return (
    <ul className="mt-1.5 space-y-0.5 text-xs">
      {event.changes.map((change) => (
        <li key={change.field} className="text-muted">
          <span className="font-medium text-ink">{change.label}:</span>{' '}
          {creating ? (
            <span className={change.kind === 'money' ? 'figures' : ''}>{formatValue(change, 'new')}</span>
          ) : (
            <>
              <span className={`line-through decoration-muted/60 ${change.kind === 'money' ? 'figures' : ''}`}>
                {formatValue(change, 'old')}
              </span>
              <span aria-hidden> → </span>
              <span className="sr-only"> cambió a </span>
              <span className={`text-ink ${change.kind === 'money' ? 'figures' : ''}`}>
                {formatValue(change, 'new')}
              </span>
            </>
          )}
        </li>
      ))}
    </ul>
  )
}

export function HistoryItem({
  event,
  showEntity = false,
  kicker,
}: {
  event: HistoryEvent
  showEntity?: boolean
  /** Rótulo opcional sobre el renglón ("Gasto", "Por pagar"…), para listas mixtas. */
  kicker?: string
}) {
  return (
    <li className="relative pb-4 pl-5 last:pb-0">
      {kicker ? (
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">{kicker}</p>
      ) : null}
      <span
        className={`absolute -left-[4.5px] top-1.5 h-2 w-2 rounded-full ring-2 ring-surface ${ACTION_DOT[event.action] ?? 'bg-muted'}`}
        aria-hidden
      />
      <p className="text-sm">
        <span className="font-medium">{event.user_name ?? 'Sistema'}</span>{' '}
        <span className="text-muted">{ACTION_LABELS[event.action]?.toLowerCase() ?? event.action}</span>
        {showEntity && event.entity_label ? <span className="font-medium"> · {event.entity_label}</span> : null}
      </p>
      <p className="text-xs text-muted">
        {formatWhen(event.created_at)}
        {event.source !== 'web' ? ` · vía ${SOURCE_LABELS[event.source] ?? event.source}` : ''}
      </p>
      <ChangeList event={event} />
      {event.reason ? (
        <p className="mt-1.5 rounded-md bg-surface-2/60 px-2 py-1 text-xs">
          <span className="font-medium">Motivo:</span> {event.reason}
        </p>
      ) : null}
    </li>
  )
}

const PAGE_SIZE = 20

/** Línea de tiempo de un registro. `endpoint` es el recurso: "/expenses", "/income", "/payables"… */
export function HistoryTimeline({ endpoint, entityId }: { endpoint: string; entityId: string }) {
  const [limit, setLimit] = useState(PAGE_SIZE)
  const query = useQuery({
    queryKey: ['history', endpoint, entityId, limit],
    queryFn: async () =>
      (await api.get<Page<HistoryEvent>>(`${endpoint}/${entityId}/history`, { params: { limit } })).data,
  })

  if (query.isLoading) return <div className="h-16 animate-pulse rounded-lg bg-surface-2" />
  if (query.isError) return <p className="text-sm text-neg">No se pudo cargar el historial.</p>
  const page = query.data
  if (!page || page.items.length === 0) {
    return (
      <p className="text-sm text-muted">
        Sin cambios registrados. Lo que se edite, pague o cancele a partir de ahora aparecerá aquí.
      </p>
    )
  }
  return (
    <div>
      <ol className="border-l border-border pl-0">
        {page.items.map((event) => (
          <HistoryItem key={event.id} event={event} />
        ))}
      </ol>
      {page.total > page.items.length ? (
        <button
          type="button"
          onClick={() => setLimit((current) => current + PAGE_SIZE)}
          className="mt-3 text-xs font-medium text-accent hover:underline"
        >
          Ver {Math.min(PAGE_SIZE, page.total - page.items.length)} cambios anteriores
        </button>
      ) : null}
    </div>
  )
}
