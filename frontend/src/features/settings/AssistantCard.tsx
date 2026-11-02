import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { Card } from '@/components/ui/Table'
import { useActiveRole } from '@/lib/companies'
import { useAuthStore } from '@/stores/authStore'
import type { AssistantStatus, AssistantUsage, Organization } from '@/types/api'

const REASONS: Record<string, string> = {
  sin_llave: 'Se activa cuando se conecte la llave de Claude.',
  deshabilitado: 'Desactivado en esta empresa.',
  sin_presupuesto: 'Presupuesto del mes agotado.',
}

function usd(value: string | number) {
  return `$${Number(value).toFixed(2)} USD`
}

/** Configuración → Agentes: el asistente de Claude, su gasto del mes y el tope. */
export function AssistantCard() {
  const queryClient = useQueryClient()
  const role = useActiveRole()
  const { organization } = useAuthStore()
  const isOwner = role === 'OWNER'
  const canSeeUsage = role === 'OWNER' || role === 'ADMIN'
  const [budget, setBudget] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const status = useQuery({
    queryKey: ['assistant-status'],
    queryFn: async () => (await api.get<AssistantStatus>('/assistant/status')).data,
  })
  const usage = useQuery({
    queryKey: ['assistant-usage'],
    queryFn: async () => (await api.get<AssistantUsage>('/assistant/usage')).data,
    enabled: canSeeUsage,
  })

  const patchMutation = useMutation({
    mutationFn: async (payload: Record<string, unknown>) =>
      (await api.patch<Organization>('/organizations/current', payload)).data,
    onSuccess: (updated) => {
      useAuthStore.setState((state) => ({
        organization: updated,
        organizations: state.organizations.map((company) => (company.id === updated.id ? updated : company)),
      }))
      setBudget(null)
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['assistant-status'] })
      void queryClient.invalidateQueries({ queryKey: ['assistant-usage'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const data = status.data
  const spent = Number(data?.spent_usd ?? 0)
  const total = Number(data?.budget_usd ?? 0)
  const ratio = total > 0 ? Math.min(spent / total, 1) : 0
  const barTone = ratio >= 0.9 ? 'bg-neg' : ratio >= 0.7 ? 'bg-warn' : 'bg-accent'
  const enabled = organization?.ai_enabled ?? true

  return (
    <Card className="mt-6 max-w-lg">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-lg font-semibold">Asistente de Claude</h2>
          <p className="mt-1 text-sm text-muted">
            Responde preguntas sobre tu negocio y propone operaciones desde{' '}
            <Link to="/asistente" className="text-accent underline">
              Asistente
            </Link>
            . Cada mes tiene un tope de gasto en dólares.
          </p>
        </div>
        {data ? (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
              data.available ? 'bg-pos/10 text-pos' : 'bg-surface-2 text-muted'
            }`}
          >
            {data.available ? 'Activo' : 'Inactivo'}
          </span>
        ) : null}
      </div>

      {data ? (
        <div className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between">
            <span className="text-muted">Modelo</span>
            <span className="figures">{data.model_name}</span>
          </div>
          <div>
            <div className="flex justify-between">
              <span className="text-muted">Gasto de este mes</span>
              <span className="figures">
                {usd(data.spent_usd)} de {usd(data.budget_usd)}
              </span>
            </div>
            <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-2">
              <div className={`h-full rounded-full ${barTone}`} style={{ width: `${ratio * 100}%` }} />
            </div>
          </div>
          {!data.available ? (
            <p className="text-xs text-muted">{REASONS[data.reason ?? ''] ?? 'No disponible.'}</p>
          ) : null}
        </div>
      ) : (
        <div className="mt-4 h-16 animate-pulse rounded-lg bg-surface-2" />
      )}

      {isOwner ? (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (budget === null) return
            patchMutation.mutate({ ai_budget_usd: budget === '' ? null : budget })
          }}
          className="mt-5 space-y-3 border-t border-border pt-4"
        >
          <TextInput
            label="Tope mensual (USD)"
            type="number"
            min="0"
            step="0.01"
            hint="Vacío = tope por default de la plataforma."
            value={budget ?? (organization?.ai_budget_usd ?? '')}
            onChange={(event) => setBudget(event.target.value)}
          />
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={budget === null || patchMutation.isPending}>
              Guardar tope
            </Button>
            <Button
              variant="secondary"
              disabled={patchMutation.isPending}
              onClick={() => patchMutation.mutate({ ai_enabled: !enabled })}
            >
              {enabled ? 'Desactivar asistente' : 'Activar asistente'}
            </Button>
          </div>
        </form>
      ) : null}

      {canSeeUsage && usage.data && usage.data.by_user.length > 0 ? (
        <div className="mt-5 border-t border-border pt-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
            Uso de {usage.data.month} por persona
          </div>
          <ul className="mt-2 divide-y divide-border text-sm">
            {usage.data.by_user.map((row) => (
              <li key={row.key} className="flex items-center justify-between py-1.5">
                <span>{row.label}</span>
                <span className="figures text-muted">
                  {row.calls} llamada{row.calls === 1 ? '' : 's'} · {usd(row.cost_usd)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  )
}
