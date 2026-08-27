import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card } from '@/components/ui/Table'
import { formatDate, formatMoney } from '@/lib/format'
import { useAccounts, useCategories } from '@/lib/hooks'
import { RecurringPanel, usePendingRecurring } from '@/features/proposals/RecurringPanel'
import type { Page, Proposal } from '@/types/api'

const KIND_LABELS: Record<string, string> = {
  INCOME: 'Ingreso',
  EXPENSE: 'Gasto',
  RECEIVABLE: 'Cuenta por cobrar',
  PAYABLE: 'Cuenta por pagar',
}

const PAYLOAD_LABELS: Record<string, string> = {
  date: 'Fecha',
  due_date: 'Vence',
  description: 'Concepto',
  amount: 'Monto',
  tax_rate: 'IVA',
  status: 'Estado',
  category_id: 'Categoría',
  financial_account_id: 'Cuenta',
  notes: 'Notas',
  payment_method: 'Método',
  reference: 'Referencia',
}

/** El orden en que un humano revisa: qué es, cuánto, con qué, cuándo. */
const PAYLOAD_ORDER = [
  'description',
  'amount',
  'tax_rate',
  'category_id',
  'financial_account_id',
  'status',
  'date',
  'due_date',
  'payment_method',
  'reference',
  'notes',
]

const STATUS_LABELS: Record<string, string> = {
  PAID: 'Pagado',
  PENDING: 'Pendiente',
  OPEN: 'Abierta',
}

/** Aprobar exige entender qué se aprueba: nada de identificadores ni de inglés. */
function PayloadDetails({
  payload,
  kind,
  names,
}: {
  payload: Record<string, unknown>
  kind: string
  names: Map<string, string>
}) {
  const entries = PAYLOAD_ORDER.filter(
    (key) => payload[key] !== null && payload[key] !== undefined && payload[key] !== '',
  )

  const labelFor = (key: string) => {
    if (key === 'financial_account_id')
      return kind === 'INCOME' || kind === 'RECEIVABLE' ? 'Entra a' : 'Se paga con'
    return PAYLOAD_LABELS[key]
  }

  const valueFor = (key: string) => {
    const raw = payload[key]
    if (key === 'amount') return formatMoney(String(raw))
    if (key === 'tax_rate') return `${Math.round(Number(raw) * 100)}%`
    if (key === 'status') return STATUS_LABELS[String(raw)] ?? String(raw)
    if (key === 'category_id' || key === 'financial_account_id')
      return names.get(String(raw)) ?? '—'
    if (key === 'date' || key === 'due_date') return formatDate(String(raw))
    return String(raw)
  }

  return (
    <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
      {entries.map((key) => (
        <div key={key}>
          <dt className="text-xs text-muted">{labelFor(key)}</dt>
          <dd className={key === 'amount' ? 'figures font-medium' : ''}>{valueFor(key)}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ProposalsPage() {
  // La pestaña vive en la URL, como en Reportes: compartible y sobrevive F5.
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('vista') === 'recurrentes' ? 'recurrentes' : 'bandeja'
  const setTab = (next: string) =>
    setSearchParams(next === 'bandeja' ? {} : { vista: next }, { replace: true })

  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('PROPOSED')
  const pendingRecurring = usePendingRecurring()
  const { data: accounts } = useAccounts()
  const { data: incomeCategories } = useCategories('INCOME')
  const { data: expenseCategories } = useCategories('EXPENSE')

  // Los identificadores del payload sólo son útiles traducidos a nombres.
  const names = useMemo(
    () =>
      new Map(
        [...(accounts ?? []), ...(incomeCategories ?? []), ...(expenseCategories ?? [])].map(
          (item) => [item.id, item.name],
        ),
      ),
    [accounts, incomeCategories, expenseCategories],
  )

  const { data, isLoading } = useQuery({
    queryKey: ['proposals', statusFilter],
    queryFn: async () =>
      (
        await api.get<Page<Proposal>>('/proposals', {
          params: statusFilter ? { status: statusFilter } : {},
        })
      ).data,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['proposals'] })
    void queryClient.invalidateQueries({ queryKey: ['proposals-count'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['income'] })
    void queryClient.invalidateQueries({ queryKey: ['expense'] })
    void queryClient.invalidateQueries({ queryKey: ['receivables'] })
    void queryClient.invalidateQueries({ queryKey: ['payables'] })
  }

  const approveMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`/proposals/${id}/approve`)
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const rejectMutation = useMutation({
    mutationFn: async ({ id, reason }: { id: string; reason: string | null }) => {
      await api.post(`/proposals/${id}/reject`, { reason })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const items = data?.items ?? []

  const tabs = (
    <div className="mb-4 flex gap-2">
      {[
        { key: 'bandeja', label: 'Bandeja' },
        { key: 'recurrentes', label: 'Recurrentes' },
      ].map((item) => (
        <button
          key={item.key}
          type="button"
          onClick={() => setTab(item.key)}
          className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
            tab === item.key
              ? 'border-accent bg-accent-soft text-accent'
              : 'border-border bg-surface text-muted hover:text-ink'
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  )

  if (tab === 'recurrentes') {
    return (
      <div>
        {tabs}
        <RecurringPanel />
      </div>
    )
  }

  return (
    <div>
      {tabs}
      <PageHeader
        title="Propuestas"
        description="Operaciones sugeridas por tus agentes. Nada se registra sin tu aprobación."
      >
        <div className="flex gap-2">
          {[
            { value: 'PROPOSED', label: 'Pendientes' },
            { value: 'APPROVED', label: 'Aprobadas' },
            { value: 'REJECTED', label: 'Rechazadas' },
          ].map((filter) => (
            <button
              key={filter.value}
              type="button"
              onClick={() => setStatusFilter(filter.value)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                statusFilter === filter.value
                  ? 'bg-accent text-on-accent'
                  : 'border border-border bg-surface text-muted hover:text-ink'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </PageHeader>

      {(pendingRecurring.data ?? 0) > 0 ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface-2/60 px-4 py-2.5 text-sm">
          <span>
            Tienes <span className="figures font-semibold">{pendingRecurring.data}</span>{' '}
            operación(es) recurrente(s) sin generar este mes.
          </span>
          <button
            type="button"
            onClick={() => setTab('recurrentes')}
            className="text-xs font-medium text-accent underline"
          >
            Ir a Recurrentes
          </button>
        </div>
      ) : null}

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        <EmptyState
          title={statusFilter === 'PROPOSED' ? 'Sin propuestas pendientes' : 'Nada por aquí'}
          message="Cuando un agente conectado a ARCA detecte una operación (una venta, un gasto, una factura), la verás aquí para aprobarla o rechazarla con un clic."
        />
      ) : (
        <div className="space-y-3">
          {items.map((proposal) => (
            <Card key={proposal.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
                      {KIND_LABELS[proposal.kind] ?? proposal.kind}
                    </span>
                    <span className="text-xs text-muted">
                      {proposal.agent_name ? `${proposal.agent_name} · ` : ''}
                      {formatDate(proposal.created_at)}
                    </span>
                  </div>
                  <p className="mt-2 font-medium">{proposal.summary}</p>
                  {proposal.evidence ? (
                    <p className="mt-1 text-sm text-muted">{proposal.evidence}</p>
                  ) : null}
                  <PayloadDetails payload={proposal.payload} kind={proposal.kind} names={names} />
                  {proposal.rejection_reason ? (
                    <p className="mt-2 text-sm text-neg">Rechazada: {proposal.rejection_reason}</p>
                  ) : null}
                </div>
                {proposal.status === 'PROPOSED' ? (
                  <div className="flex shrink-0 gap-2">
                    <Button
                      onClick={() => approveMutation.mutate(proposal.id)}
                      disabled={approveMutation.isPending}
                    >
                      Aprobar
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        const reason = window.prompt('¿Por qué la rechazas? (opcional)')
                        rejectMutation.mutate({ id: proposal.id, reason: reason || null })
                      }}
                      disabled={rejectMutation.isPending}
                    >
                      Rechazar
                    </Button>
                  </div>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
