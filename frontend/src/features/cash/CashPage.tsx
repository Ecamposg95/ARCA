import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { TableFooter } from '@/components/ui/Pagination'
import { Card, Table } from '@/components/ui/Table'
import { useActiveRole } from '@/lib/companies'
import { formatDate, formatMoney, today } from '@/lib/format'
import { useAccounts, useDimensions } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'
import type { CashCut, CashCutStatus, Page, TodayCashRow } from '@/types/api'

const STATUS_LABELS: Record<CashCutStatus, { label: string; className: string }> = {
  OPEN: { label: 'Por contar', className: 'bg-warn/10 text-warn' },
  COUNTED: { label: 'Contado', className: 'bg-accent/10 text-accent' },
  DELIVERED: { label: 'Entregado', className: 'bg-pos/10 text-pos' },
  CANCELLED: { label: 'Cancelado', className: 'bg-muted/10 text-muted' },
}

const ADMIN_ROLES = ['OWNER', 'ADMIN']
const LIMIT = 20

function CutStatus({ cut }: { cut: CashCut }) {
  const config = STATUS_LABELS[cut.status]
  const received = cut.status === 'DELIVERED' && cut.received_at
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${config.className}`}>
      {received ? 'Recibido' : config.label}
    </span>
  )
}

/** La página de Caja: hoy por caja, el corte en curso y el historial. */
export function CashPage() {
  const queryClient = useQueryClient()
  const { data: accounts, isLoading: accountsLoading } = useAccounts()
  const { units, hasUnits } = useDimensions()
  const [selected, setSelected] = useState<CashCut | null>(null)
  const [filters, setFiltersState] = useState({ status: '', business_unit_id: '', account_id: '' })
  const [offset, setOffset] = useState(0)
  const setFilters = (next: Partial<typeof filters>) => {
    setFiltersState({ ...filters, ...next })
    setOffset(0)
  }

  const { data: todayRows, isLoading: todayLoading } = useQuery({
    queryKey: ['cash-cuts', 'today'],
    queryFn: async () => (await api.get<TodayCashRow[]>('/cash-cuts/today')).data,
  })
  const { data: history } = useQuery({
    queryKey: ['cash-cuts', 'list', filters, offset],
    queryFn: async () =>
      (
        await api.get<Page<CashCut>>('/cash-cuts', {
          params: {
            limit: LIMIT,
            offset,
            status: filters.status || undefined,
            business_unit_id: filters.business_unit_id || undefined,
            account_id: filters.account_id || undefined,
          },
        })
      ).data,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['cash-cuts'] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['transactions'] })
  }

  const openMutation = useMutation({
    mutationFn: async (accountId: string) =>
      (await api.post<CashCut>('/cash-cuts', { financial_account_id: accountId, date: today() })).data,
    onSuccess: (cut) => {
      invalidate()
      setSelected(cut)
    },
    onError: (err) => window.alert(errorMessage(err)),
  })

  const cashAccounts = (accounts ?? []).filter((account) => account.type === 'CASH' && account.active)

  return (
    <div>
      <PageHeader
        title="Caja"
        description="El corte de cada caja: lo que debía haber, lo que contaste y a quién se lo entregaste."
      />

      {accountsLoading || todayLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : cashAccounts.length === 0 ? (
        <EmptyState
          title="Sin cajas de efectivo"
          message="Da de alta una caja de efectivo para hacer cortes."
          action={
            <Link to="/cuentas?nueva=1">
              <Button>Agregar caja</Button>
            </Link>
          }
        />
      ) : (
        <>
          <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Hoy</h2>
          <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(todayRows ?? []).map((row) => (
              <Card key={row.account_id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium">{row.account_name}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {row.business_unit_name ?? 'Efectivo'}
                    </div>
                  </div>
                  <div className="text-right">
                    <Money value={row.current_balance} size="lg" tone={Number(row.current_balance) < 0 ? 'neg' : 'ink'} />
                    <div className="text-[10px] uppercase tracking-wide text-muted">en caja</div>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-border pt-2.5">
                  {row.cut ? (
                    <>
                      <CutStatus cut={row.cut} />
                      <Button variant="secondary" className="!px-2.5 !py-1 text-xs" onClick={() => setSelected(row.cut)}>
                        {row.cut.status === 'OPEN' ? 'Contar' : 'Ver corte'}
                      </Button>
                    </>
                  ) : (
                    <>
                      <span className="text-xs text-muted">Sin corte hoy</span>
                      <Button
                        className="!px-2.5 !py-1 text-xs"
                        disabled={openMutation.isPending}
                        onClick={() => openMutation.mutate(row.account_id)}
                      >
                        Hacer corte
                      </Button>
                    </>
                  )}
                </div>
              </Card>
            ))}
          </div>

          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Historial de cortes</h2>
            <div className="flex flex-wrap gap-2">
              <select
                aria-label="Caja"
                className="rounded border border-border bg-surface px-2.5 py-1.5 text-xs text-ink"
                value={filters.account_id}
                onChange={(event) => setFilters({ account_id: event.target.value })}
              >
                <option value="">Todas las cajas</option>
                {cashAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </select>
              {hasUnits ? (
                <select
                  aria-label="Unidad"
                  className="rounded border border-border bg-surface px-2.5 py-1.5 text-xs text-ink"
                  value={filters.business_unit_id}
                  onChange={(event) => setFilters({ business_unit_id: event.target.value })}
                >
                  <option value="">Todas las unidades</option>
                  {units.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
              ) : null}
              <select
                aria-label="Estado"
                className="rounded border border-border bg-surface px-2.5 py-1.5 text-xs text-ink"
                value={filters.status}
                onChange={(event) => setFilters({ status: event.target.value })}
              >
                <option value="">Todos los estados</option>
                {(Object.keys(STATUS_LABELS) as CashCutStatus[]).map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status].label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {history && history.items.length === 0 ? (
            <EmptyState
              title="Todavía no hay cortes"
              message="Al final del día, haz el corte de cada caja: cuenta el efectivo y entrégalo."
            />
          ) : (
            <Table
              headers={['Fecha', 'Caja', ...(hasUnits ? ['Unidad'] : []), 'Esperado', 'Contado', 'Diferencia', 'Entregado', 'Estado']}
              secondary={hasUnits ? [3, 4, 7] : [3, 6]}
              footer={history ? <TableFooter page={history} onOffsetChange={setOffset} noun="cortes" /> : null}
            >
              {(history?.items ?? []).map((cut) => {
                const difference = Number(cut.difference ?? 0)
                return (
                  <tr
                    key={cut.id}
                    className="cursor-pointer transition-colors hover:bg-surface-2"
                    onClick={() => setSelected(cut)}
                  >
                    <td className="whitespace-nowrap px-4 py-2.5">{formatDate(cut.date)}</td>
                    <td className="px-4 py-2.5">{cut.account_name}</td>
                    {hasUnits ? <td className="px-4 py-2.5 text-muted">{cut.business_unit_name ?? '—'}</td> : null}
                    <td className="figures px-4 py-2.5 text-right">{formatMoney(cut.expected_closing)}</td>
                    <td className="figures px-4 py-2.5 text-right">
                      {cut.counted_amount !== null ? formatMoney(cut.counted_amount) : '—'}
                    </td>
                    <td
                      className={`figures px-4 py-2.5 text-right ${
                        difference < 0 ? 'text-neg' : difference > 0 ? 'text-pos' : 'text-muted'
                      }`}
                    >
                      {cut.difference !== null ? formatMoney(cut.difference) : '—'}
                    </td>
                    <td className="figures px-4 py-2.5 text-right">
                      {cut.delivered_amount !== null ? formatMoney(cut.delivered_amount) : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <CutStatus cut={cut} />
                    </td>
                  </tr>
                )
              })}
            </Table>
          )}
        </>
      )}

      {selected ? (
        <CutModal
          key={selected.id + selected.status + (selected.received_at ?? '')}
          cut={selected}
          onClose={() => setSelected(null)}
          onChanged={(next) => {
            invalidate()
            setSelected(next)
          }}
        />
      ) : null}
    </div>
  )
}

/** Un corte en detalle: contar, entregar, confirmar, cancelar. */
function CutModal({
  cut,
  onClose,
  onChanged,
}: {
  cut: CashCut
  onClose: () => void
  onChanged: (next: CashCut | null) => void
}) {
  const role = useActiveRole()
  const userId = useAuthStore((state) => state.user?.id ?? null)
  const isAdmin = role !== null && ADMIN_ROLES.includes(role)
  const { data: accounts } = useAccounts()
  const [error, setError] = useState<string | null>(null)
  const [counted, setCounted] = useState(cut.counted_amount ?? '')
  const [explanation, setExplanation] = useState(cut.explanation ?? '')
  const [deliver, setDeliver] = useState({ amount: cut.counted_amount ?? '', to_account_id: '' })
  const [recounting, setRecounting] = useState(false)

  const expected = Number(cut.expected_closing)
  const liveDifference = counted === '' ? null : Number(counted) - expected
  const destinations = (accounts ?? []).filter(
    (account) => account.active && account.id !== cut.financial_account_id && (account.type === 'CASH' || account.type === 'BANK'),
  )

  function useAction<T>(run: () => Promise<T>) {
    return useMutation({
      mutationFn: run,
      onSuccess: (result) => {
        setError(null)
        onChanged(result as CashCut | null)
      },
      onError: (err) => setError(errorMessage(err)),
    })
  }
  const countMutation = useAction(async () => {
    const payload: Record<string, unknown> = { counted_amount: counted }
    if (explanation) payload.explanation = explanation
    return (await api.post<CashCut>(`/cash-cuts/${cut.id}/count`, payload)).data
  })
  const deliverMutation = useAction(
    async () =>
      (
        await api.post<CashCut>(`/cash-cuts/${cut.id}/deliver`, {
          delivered_amount: deliver.amount,
          delivered_to_account_id: deliver.to_account_id,
        })
      ).data,
  )
  const confirmMutation = useAction(async () => (await api.post<CashCut>(`/cash-cuts/${cut.id}/confirm-receipt`)).data)
  const cancelMutation = useAction(async () => (await api.delete<CashCut>(`/cash-cuts/${cut.id}`)).data)

  const canCount = cut.status === 'OPEN' || (cut.status === 'COUNTED' && recounting)
  const canConfirm = cut.status === 'DELIVERED' && !cut.received_at && (cut.delivered_by !== userId || isAdmin)

  return (
    <Modal title={`Corte · ${cut.account_name ?? 'Caja'} · ${formatDate(cut.date)}`} open onClose={onClose} size="lg">
      <div className="space-y-5">
        <div className="flex items-center gap-2">
          <CutStatus cut={cut} />
          {cut.business_unit_name ? <span className="text-xs text-muted">{cut.business_unit_name}</span> : null}
        </div>

        {/* Lo que debía haber: apertura + entradas − salidas. */}
        <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-surface-2 p-3 sm:grid-cols-4">
          {[
            { label: 'Apertura', value: cut.opening_balance, tone: 'ink' as const },
            { label: 'Entradas', value: cut.inflows, tone: 'pos' as const },
            { label: 'Salidas', value: cut.outflows, tone: 'neg' as const },
            { label: 'Esperado', value: cut.expected_closing, tone: 'ink' as const },
          ].map((item) => (
            <div key={item.label}>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">{item.label}</div>
              <div className="mt-0.5">
                <Money value={item.value} tone={item.tone} />
              </div>
            </div>
          ))}
        </div>

        {canCount ? (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              countMutation.mutate()
            }}
            className="space-y-3"
          >
            <div className="grid grid-cols-2 gap-4">
              <TextInput
                label="¿Cuánto contaste?"
                type="number"
                min="0"
                step="0.01"
                required
                autoFocus
                value={counted}
                onChange={(event) => setCounted(event.target.value)}
              />
              <div className="space-y-1">
                <div className="text-[11px] font-semibold tracking-wide text-muted">Diferencia</div>
                <div className="py-2.5">
                  {liveDifference === null ? (
                    <span className="text-sm text-muted">—</span>
                  ) : (
                    <Money
                      value={liveDifference}
                      size="lg"
                      tone={liveDifference < 0 ? 'neg' : liveDifference > 0 ? 'pos' : 'ink'}
                    />
                  )}
                </div>
              </div>
            </div>
            {liveDifference !== null && liveDifference !== 0 ? (
              <TextInput
                label={liveDifference < 0 ? '¿Por qué falta?' : '¿Por qué sobra?'}
                required
                placeholder="Explica la diferencia"
                maxLength={500}
                value={explanation}
                onChange={(event) => setExplanation(event.target.value)}
                hint={
                  liveDifference < 0
                    ? 'El faltante se registra como gasto para que la caja quede en lo contado.'
                    : 'El sobrante se registra como ingreso para que la caja quede en lo contado.'
                }
              />
            ) : null}
            {error ? <p className="text-sm text-neg">{error}</p> : null}
            <div className="flex justify-end gap-2">
              {recounting ? (
                <Button variant="ghost" onClick={() => setRecounting(false)}>
                  Cancelar
                </Button>
              ) : null}
              <Button type="submit" disabled={countMutation.isPending}>
                {countMutation.isPending ? 'Guardando…' : 'Guardar conteo'}
              </Button>
            </div>
          </form>
        ) : null}

        {cut.status !== 'OPEN' && !canCount ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Contado</div>
              <div className="mt-0.5">
                <Money value={cut.counted_amount} />
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Diferencia</div>
              <div className="mt-0.5">
                <Money
                  value={cut.difference}
                  tone={Number(cut.difference) < 0 ? 'neg' : Number(cut.difference) > 0 ? 'pos' : 'ink'}
                />
              </div>
            </div>
            {cut.explanation ? (
              <div className="col-span-2 sm:col-span-1">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Explicación</div>
                <div className="mt-0.5 text-sm">{cut.explanation}</div>
              </div>
            ) : null}
          </div>
        ) : null}

        {cut.status === 'COUNTED' && !recounting ? (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              deliverMutation.mutate()
            }}
            className="space-y-3 border-t border-border pt-4"
          >
            <h3 className="text-sm font-medium">Entregar el efectivo</h3>
            <div className="grid grid-cols-2 gap-4">
              <TextInput
                label="¿Cuánto entregas?"
                type="number"
                min="0.01"
                max={cut.counted_amount ?? undefined}
                step="0.01"
                required
                value={deliver.amount}
                onChange={(event) => setDeliver({ ...deliver, amount: event.target.value })}
                hint="Lo que se queda en caja sigue contando como disponible."
              />
              <SelectInput
                label="¿A dónde?"
                required
                placeholder="Caja central o banco"
                options={destinations.map((account) => ({ value: account.id, label: account.name }))}
                value={deliver.to_account_id}
                onChange={(event) => setDeliver({ ...deliver, to_account_id: event.target.value })}
              />
            </div>
            {error ? <p className="text-sm text-neg">{error}</p> : null}
            <div className="flex flex-wrap justify-end gap-2">
              <Button variant="ghost" onClick={() => setRecounting(true)}>
                Volver a contar
              </Button>
              <Button type="submit" disabled={deliverMutation.isPending}>
                {deliverMutation.isPending ? 'Entregando…' : 'Entregar'}
              </Button>
            </div>
          </form>
        ) : null}

        {cut.status === 'DELIVERED' ? (
          <div className="space-y-3 border-t border-border pt-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Entregado</div>
                <div className="mt-0.5">
                  <Money value={cut.delivered_amount} />
                </div>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">A</div>
                <div className="mt-0.5 text-sm">{cut.delivered_to_account_name}</div>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wide text-muted">Entregó</div>
                <div className="mt-0.5 text-sm">{cut.delivered_by_name ?? '—'}</div>
              </div>
            </div>
            {cut.received_at ? (
              <p className="text-sm text-muted">
                Recibió <span className="text-ink">{cut.received_by_name}</span> · {formatDate(cut.received_at)}
              </p>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-muted">
                  {canConfirm ? 'Confirma que recibiste este efectivo.' : 'Pendiente de que quien recibe lo confirme.'}
                </p>
                {canConfirm ? (
                  <Button disabled={confirmMutation.isPending} onClick={() => confirmMutation.mutate()}>
                    Confirmar recepción
                  </Button>
                ) : null}
              </div>
            )}
            {error ? <p className="text-sm text-neg">{error}</p> : null}
          </div>
        ) : null}

        {isAdmin && cut.status !== 'CANCELLED' ? (
          <div className="flex justify-end border-t border-border pt-3">
            <Button
              variant="danger"
              className="!px-2.5 !py-1 text-xs"
              disabled={cancelMutation.isPending}
              onClick={() => {
                if (window.confirm('¿Cancelar este corte? Se revierten la entrega y el ajuste, si los hay.')) {
                  cancelMutation.mutate()
                }
              }}
            >
              Cancelar corte
            </Button>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}
