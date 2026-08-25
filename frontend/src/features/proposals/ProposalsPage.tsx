import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card } from '@/components/ui/Table'
import { formatDate, formatMoney } from '@/lib/format'
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
  status: 'Estado',
  notes: 'Notas',
  payment_method: 'Método',
  reference: 'Referencia',
}

function PayloadDetails({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload).filter(
    ([key, value]) => value !== null && value !== undefined && PAYLOAD_LABELS[key],
  )
  return (
    <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs text-muted">{PAYLOAD_LABELS[key]}</dt>
          <dd className={key === 'amount' ? 'figures font-medium' : ''}>
            {key === 'amount' ? formatMoney(String(value)) : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function ProposalsPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('PROPOSED')

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

  return (
    <div>
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
                  <PayloadDetails payload={proposal.payload} />
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
