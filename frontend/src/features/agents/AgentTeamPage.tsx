/** El equipo de agentes residentes: cinco especialistas, cinco preguntas.
 *
 *  Cada tarjeta ES un agente: su pregunta como título, y su brief calculado
 *  sobre el libro real de la empresa — headline, métricas, hallazgos y
 *  recomendaciones. Determinista y auditable hoy; el día que un modelo tome el
 *  volante, la forma del brief no cambia (es la misma de los ejecutivos de
 *  Cortex).
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  BookOpenCheck,
  Compass,
  HandCoins,
  TrendingUp,
  Vault,
  type LucideIcon,
} from 'lucide-react'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'

const ICONS: Record<string, LucideIcon> = {
  cfo: Compass,
  treasury: Vault,
  collections: HandCoins,
  accounting: BookOpenCheck,
  forecast: TrendingUp,
}

interface Metric {
  label: string
  value: string
  hint?: string
  tone?: 'pos' | 'neg' | 'warn' | null
}

interface Brief {
  id: string
  name: string
  question: string
  topics: string[]
  headline: string
  metrics: Metric[]
  findings: string[]
  recommendations: string[]
}

function toneClass(tone?: Metric['tone']) {
  if (tone === 'pos') return 'text-pos'
  if (tone === 'neg') return 'text-neg'
  if (tone === 'warn') return 'text-warn'
  return ''
}

function AgentCard({ agentId, monthlyCost }: { agentId: string; monthlyCost: string }) {
  const query = useQuery({
    queryKey: ['agent-team', agentId, agentId === 'forecast' ? monthlyCost : null],
    queryFn: async () =>
      (
        await api.get<Brief>(`/agent-team/${agentId}/brief`, {
          params: agentId === 'forecast' ? { monthly_cost: monthlyCost } : {},
        })
      ).data,
  })

  const brief = query.data
  const Icon = ICONS[agentId] ?? Compass

  return (
    <div className="flex flex-col rounded-xl border border-border bg-surface p-4 shadow-card">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-accent-soft p-2 text-accent">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <p className="figures text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
            {brief?.name ?? agentId}
          </p>
          <h2 className="font-display text-[15px] font-bold leading-snug tracking-tight">
            {brief?.question ?? '…'}
          </h2>
        </div>
      </div>

      {brief ? (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {brief.topics.map((topic) => (
              <span
                key={topic}
                className="rounded-full bg-surface-2 px-2 py-0.5 text-[10px] font-medium text-muted"
              >
                {topic}
              </span>
            ))}
          </div>

          <p className="mt-3 text-sm font-medium leading-snug">{brief.headline}</p>

          <div className="mt-3 grid grid-cols-2 gap-2">
            {brief.metrics.map((metric) => (
              <div key={metric.label} className="rounded-lg bg-surface-2/60 px-2.5 py-1.5">
                <p className="figures text-[9px] uppercase tracking-[0.14em] text-muted">
                  {metric.label}
                </p>
                <p className={`figures text-[13px] font-semibold ${toneClass(metric.tone)}`}>
                  {metric.value}
                  {metric.hint ? (
                    <span className="ml-1 text-[10px] font-normal text-muted">{metric.hint}</span>
                  ) : null}
                </p>
              </div>
            ))}
          </div>

          <ul className="mt-3 flex-1 space-y-1.5 text-[13px] leading-snug text-ink-2">
            {brief.findings.map((finding, index) => (
              <li key={index} className="flex gap-2">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-accent" />
                <span>{finding}</span>
              </li>
            ))}
          </ul>

          <div className="mt-3 border-t border-border pt-2.5">
            {brief.recommendations.map((rec, index) => (
              <p key={index} className="text-[11.5px] leading-snug text-muted">
                → {rec}
              </p>
            ))}
          </div>
        </>
      ) : query.isError ? (
        <p className="mt-4 text-sm text-neg">Este agente no pudo leer los libros. Reintenta.</p>
      ) : (
        <div className="mt-4 space-y-2">
          <div className="h-4 w-3/4 animate-pulse rounded bg-surface-2" />
          <div className="h-16 animate-pulse rounded bg-surface-2" />
          <div className="h-24 animate-pulse rounded bg-surface-2" />
        </div>
      )}
    </div>
  )
}

export function AgentTeamPage() {
  const [monthlyCost, setMonthlyCost] = useState('35000')

  const roster = useQuery({
    queryKey: ['agent-team'],
    queryFn: async () =>
      (await api.get<{ items: { id: string }[] }>('/agent-team')).data.items,
  })

  return (
    <div>
      <PageHeader
        title="Agentes"
        description="Cinco especialistas leen tus libros y responden una pregunta cada uno. Nada se registra sin tu aprobación."
        actions={
          <label className="flex items-center gap-2 text-xs text-muted">
            Costo por contratación
            <input
              type="number"
              min="1000"
              step="1000"
              value={monthlyCost}
              onChange={(event) => setMonthlyCost(event.target.value)}
              className="figures w-24 rounded-lg border border-border bg-surface px-2 py-1.5 text-right text-sm text-ink"
            />
            <span className="figures">/mes</span>
          </label>
        }
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(roster.data ?? []).map((agent) => (
          <AgentCard key={agent.id} agentId={agent.id} monthlyCost={monthlyCost} />
        ))}
      </div>

      <p className="mt-6 max-w-3xl text-xs leading-relaxed text-muted">
        Cada cifra sale del libro contable — los mismos servicios que alimentan Reportes y el
        terminal de Análisis. El razonamiento de estos agentes es determinista y auditable; cuando
        un modelo tome el volante (Atlas Cortex o Claude vía MCP), la forma del brief no cambia:
        sólo cambia quién lo piensa.
      </p>
    </div>
  )
}
