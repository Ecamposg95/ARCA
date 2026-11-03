/** Historial de cambios de toda la empresa (HU-09): quién cambió qué, con filtros. */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { HistoryItem } from '@/components/ui/HistoryTimeline'
import { TableFooter } from '@/components/ui/Pagination'
import { Card } from '@/components/ui/Table'
import type { HistoryEvent, Page } from '@/types/api'

const ENTITY_OPTIONS = [
  { value: 'expense', label: 'Gastos' },
  { value: 'income', label: 'Ingresos' },
  { value: 'payable', label: 'Cuentas por pagar' },
  { value: 'receivable', label: 'Cuentas por cobrar' },
  { value: 'financial_account', label: 'Cuentas de dinero' },
  { value: 'proposal', label: 'Autorizaciones y propuestas' },
]

const ENTITY_NOUN: Record<string, string> = {
  expense: 'Gasto',
  income: 'Ingreso',
  payable: 'Por pagar',
  receivable: 'Por cobrar',
  financial_account: 'Cuenta',
  category: 'Categoría',
  proposal: 'Propuesta',
}

export function HistoryCard() {
  const [filters, setFilters] = useState({ user_id: '', entity_type: '', from: '', to: '' })
  const [offset, setOffset] = useState(0)

  const { data: members } = useQuery({
    queryKey: ['members'],
    queryFn: async () =>
      (await api.get<{ items: { user_id: string; name: string }[] }>('/organizations/current/members')).data
        .items,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['history', 'all', filters, offset],
    queryFn: async () =>
      (
        await api.get<Page<HistoryEvent>>('/history', {
          params: {
            ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
            limit: 25,
            offset,
          },
        })
      ).data,
  })

  function setFilter(patch: Partial<typeof filters>) {
    setFilters((current) => ({ ...current, ...patch }))
    setOffset(0)
  }

  const items = data?.items ?? []

  return (
    <Card className="mt-6">
      <h2 className="font-display text-lg font-semibold">Historial de cambios</h2>
      <p className="mt-1 text-sm text-muted">
        Quién registró, editó, pagó o canceló cada operación, y cuáles eran los valores anteriores.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <SelectInput
          label="Persona"
          placeholder="Todo el equipo"
          options={(members ?? []).map((member) => ({ value: member.user_id, label: member.name }))}
          value={filters.user_id}
          onChange={(event) => setFilter({ user_id: event.target.value })}
        />
        <SelectInput
          label="Qué"
          placeholder="Todo"
          options={ENTITY_OPTIONS}
          value={filters.entity_type}
          onChange={(event) => setFilter({ entity_type: event.target.value })}
        />
        <TextInput
          label="Desde"
          type="date"
          value={filters.from}
          onChange={(event) => setFilter({ from: event.target.value })}
        />
        <TextInput
          label="Hasta"
          type="date"
          value={filters.to}
          onChange={(event) => setFilter({ to: event.target.value })}
        />
      </div>

      <div className="mt-5">
        {isLoading ? (
          <div className="h-24 animate-pulse rounded-lg bg-surface-2" />
        ) : items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted">
            No hay cambios con estos filtros. Cuando alguien registre o corrija una operación, aparecerá aquí.
          </p>
        ) : (
          <>
            <ol className="border-l border-border">
              {items.map((event) => (
                <HistoryItem
                  key={event.id}
                  event={event}
                  showEntity
                  kicker={ENTITY_NOUN[event.entity_type] ?? event.entity_type}
                />
              ))}
            </ol>
            <div className="mt-3 -mx-5 -mb-5">
              <TableFooter page={data!} onOffsetChange={setOffset} noun="cambios" />
            </div>
          </>
        )}
      </div>
    </Card>
  )
}
