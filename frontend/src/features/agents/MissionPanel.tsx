/** Misión en vivo — el teatro agéntico de ARCA, al estilo Mission Control de
 *  Atlas Cortex: roster con estados que brillan, feed con timestamps, compuerta
 *  de aprobación humana y brief ejecutivo final.
 *
 *  La diferencia con el teatro puro de Cortex: aquí el guion INTERPOLA los
 *  números reales de los cinco briefs del backend. La coreografía es fija y
 *  determinista (nada de Math.random en el orden); las cifras son del libro.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import {
  BookOpenCheck,
  Compass,
  HandCoins,
  TrendingUp,
  Vault,
  type LucideIcon,
} from 'lucide-react'
import { api } from '@/api/client'
import { Button } from '@/components/ui/Button'

type AgentId = 'cfo' | 'treasury' | 'collections' | 'accounting' | 'forecast'
type Status = 'IDLE' | 'PERCIBIENDO' | 'RAZONANDO' | 'ACTUANDO' | 'ESPERA' | 'LISTO'
type ActionType = 'LEE' | 'RAZONA' | 'ACTÚA' | 'PROPONE' | 'HANDOFF'

interface MissionAgent {
  id: AgentId
  name: string
  role: string
  icon: LucideIcon
  color: string
}

const AGENTS: MissionAgent[] = [
  { id: 'cfo', name: 'CFO Agent', role: 'Runway & escenarios', icon: Compass, color: '#2c9aa6' },
  { id: 'treasury', name: 'Treasury Agent', role: 'Pagos & prioridad', icon: Vault, color: '#c9a24b' },
  { id: 'collections', name: 'Collections Agent', role: 'Cartera & cobranza', icon: HandCoins, color: '#d76f8e' },
  { id: 'accounting', name: 'Accounting Agent', role: 'Variaciones & margen', icon: BookOpenCheck, color: '#7b6ef0' },
  { id: 'forecast', name: 'Forecast Agent', role: 'Contratación & futuro', icon: TrendingUp, color: '#4ca374' },
]

interface Brief {
  id: string
  headline: string
  metrics: { label: string; value: string }[]
  findings: string[]
  recommendations: string[]
}

interface FeedEntry {
  id: number
  time: string
  agentId: AgentId
  type: ActionType
  message: string
}

interface Step {
  atMs: number
  agentId: AgentId
  type: ActionType
  status: Status
  message: (b: Record<AgentId, Brief>) => string
  also?: { agentId: AgentId; status: Status }[]
  approval?: boolean
  final?: boolean
}

/* La coreografía. Tiempos fijos; textos con números reales del libro. */
const PRE_APPROVAL: Step[] = [
  {
    atMs: 400,
    agentId: 'cfo',
    type: 'LEE',
    status: 'PERCIBIENDO',
    message: () => 'Revisión semanal iniciada — leyendo caja, serie de 90 días y compromisos.',
  },
  {
    atMs: 1900,
    agentId: 'cfo',
    type: 'RAZONA',
    status: 'RAZONANDO',
    message: (b) => `${metric(b.cfo, 'Caja')} en caja. ${b.cfo.headline}`,
  },
  {
    atMs: 3400,
    agentId: 'cfo',
    type: 'HANDOFF',
    status: 'ACTUANDO',
    message: () => 'Pido el detalle de cartera a Collections y la cola de pagos a Treasury.',
    also: [
      { agentId: 'collections', status: 'PERCIBIENDO' },
      { agentId: 'treasury', status: 'PERCIBIENDO' },
    ],
  },
  {
    atMs: 4900,
    agentId: 'collections',
    type: 'LEE',
    status: 'PERCIBIENDO',
    message: () => 'Barriendo AR por tramos de antigüedad y midiendo concentración por cliente…',
  },
  {
    atMs: 6400,
    agentId: 'collections',
    type: 'RAZONA',
    status: 'RAZONANDO',
    message: (b) => b.collections.findings[0] ?? b.collections.headline,
  },
  {
    atMs: 7900,
    agentId: 'treasury',
    type: 'RAZONA',
    status: 'RAZONANDO',
    message: (b) => b.treasury.headline,
  },
  {
    atMs: 9400,
    agentId: 'accounting',
    type: 'LEE',
    status: 'PERCIBIENDO',
    message: () => 'Cruzando el mes contra el MISMO corte del mes anterior — nunca contra el mes completo.',
  },
  {
    atMs: 10900,
    agentId: 'accounting',
    type: 'RAZONA',
    status: 'RAZONANDO',
    message: (b) => `${b.accounting.findings[0] ?? ''} ${b.accounting.findings[2] ?? ''}`.trim(),
  },
  {
    atMs: 12400,
    agentId: 'forecast',
    type: 'LEE',
    status: 'PERCIBIENDO',
    message: () => 'Corriendo escenarios de contratación sobre el flujo real: base, conservador, growth…',
  },
  {
    atMs: 13900,
    agentId: 'forecast',
    type: 'RAZONA',
    status: 'RAZONANDO',
    message: (b) => b.forecast.headline,
    also: [
      { agentId: 'collections', status: 'LISTO' },
      { agentId: 'treasury', status: 'LISTO' },
      { agentId: 'accounting', status: 'LISTO' },
    ],
  },
  {
    atMs: 15400,
    agentId: 'cfo',
    type: 'PROPONE',
    status: 'ESPERA',
    message: (b) =>
      `Síntesis lista: ${b.collections.metrics.find((m) => m.label === 'Vencido')?.value ?? 'cartera'} vencidos son el hallazgo accionable. Propongo activar la cobranza — espera aprobación humana.`,
    also: [{ agentId: 'forecast', status: 'LISTO' }],
    approval: true,
  },
]

const POST_APPROVAL: Step[] = [
  {
    atMs: 400,
    agentId: 'cfo',
    type: 'ACTÚA',
    status: 'ACTUANDO',
    message: () => 'Aprobado. La propuesta de cobranza queda lista para la bandeja — la decisión fue tuya, no mía.',
  },
  {
    atMs: 1900,
    agentId: 'collections',
    type: 'ACTÚA',
    status: 'ACTUANDO',
    message: (b) =>
      `Preparando la llamada de cobranza con el desglose por tramo y el DSO (${metric(b.collections, 'DSO')}).`,
  },
  {
    atMs: 3400,
    agentId: 'cfo',
    type: 'HANDOFF',
    status: 'LISTO',
    message: () => 'Brief semanal publicado. Handoff al dueño: cinco preguntas respondidas, una acción esperando tu clic.',
    also: [{ agentId: 'collections', status: 'LISTO' }],
    final: true,
  },
]

function metric(brief: Brief | undefined, label: string): string {
  return brief?.metrics.find((m) => m.label === label)?.value ?? '—'
}

const STATUS_LABEL: Record<Status, string> = {
  IDLE: 'En espera',
  PERCIBIENDO: 'Leyendo el libro',
  RAZONANDO: 'Razonando',
  ACTUANDO: 'Actuando',
  ESPERA: 'Espera aprobación',
  LISTO: 'Listo',
}

const ACTIVE: Status[] = ['PERCIBIENDO', 'RAZONANDO', 'ACTUANDO']

function statusColor(status: Status, accent: string): string {
  switch (status) {
    case 'PERCIBIENDO':
      return 'hsl(var(--accent))'
    case 'RAZONANDO':
      return accent
    case 'ACTUANDO':
      return accent
    case 'ESPERA':
      return 'hsl(var(--warn))'
    case 'LISTO':
      return 'hsl(var(--pos))'
    default:
      return 'hsl(var(--muted))'
  }
}

const idleStatuses = (): Record<AgentId, Status> => ({
  cfo: 'IDLE',
  treasury: 'IDLE',
  collections: 'IDLE',
  accounting: 'IDLE',
  forecast: 'IDLE',
})

type Phase = 'idle' | 'running' | 'awaiting' | 'executing' | 'complete'

export function MissionPanel() {
  const briefQueries = useQueries({
    queries: AGENTS.map((agent) => ({
      queryKey: ['agent-team', agent.id, null],
      queryFn: async () => (await api.get<Brief>(`/agent-team/${agent.id}/brief`)).data,
      staleTime: 60_000,
    })),
  })
  const briefs = useMemo(() => {
    const map = {} as Record<AgentId, Brief>
    briefQueries.forEach((query, index) => {
      if (query.data) map[AGENTS[index].id] = query.data
    })
    return map
  }, [briefQueries])
  const ready = AGENTS.every((agent) => briefs[agent.id])

  const [phase, setPhase] = useState<Phase>('idle')
  const [statuses, setStatuses] = useState<Record<AgentId, Status>>(idleStatuses)
  const [feed, setFeed] = useState<FeedEntry[]>([])
  const timers = useRef<number[]>([])
  const feedRef = useRef<HTMLDivElement>(null)
  const entryId = useRef(0)

  // Limpieza dura: una misión abandonada no debe seguir disparando timeouts.
  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight })
  }, [feed])

  const stamp = () =>
    new Date().toLocaleTimeString('es-MX', { hour12: false })

  function runSegment(steps: Step[], onDone: (last: Step) => void) {
    steps.forEach((step) => {
      const timer = window.setTimeout(() => {
        setStatuses((current) => {
          const next = { ...current, [step.agentId]: step.status }
          step.also?.forEach((extra) => {
            next[extra.agentId] = extra.status
          })
          return next
        })
        setFeed((current) => [
          ...current,
          {
            id: entryId.current++,
            time: stamp(),
            agentId: step.agentId,
            type: step.type,
            message: step.message(briefs),
          },
        ])
        if (step === steps[steps.length - 1]) onDone(step)
      }, step.atMs)
      timers.current.push(timer)
    })
  }

  function launch() {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setFeed([])
    setStatuses(idleStatuses())
    setPhase('running')
    runSegment(PRE_APPROVAL, () => setPhase('awaiting'))
  }

  function approve() {
    setPhase('executing')
    runSegment(POST_APPROVAL, () => setPhase('complete'))
  }

  const cfoBrief = briefs.cfo

  return (
    <div className="space-y-4">
      {/* ── Barra de misión ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3 shadow-card">
        <div>
          <p className="figures text-[10px] font-semibold uppercase tracking-[0.16em] text-accent">
            Misión · revisión semanal de finanzas
          </p>
          <p className="text-sm text-muted">
            Cinco agentes leen el libro real, se pasan la estafeta y UNA acción espera tu aprobación.
          </p>
        </div>
        <Button onClick={launch} disabled={!ready || phase === 'running' || phase === 'executing'}>
          {phase === 'idle' ? '▶ Lanzar misión' : phase === 'complete' ? '↻ Repetir misión' : 'En curso…'}
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        {/* ── Roster ── */}
        <div className="space-y-2 lg:col-span-2">
          {AGENTS.map((agent) => {
            const status = statuses[agent.id]
            const active = ACTIVE.includes(status)
            const color = statusColor(status, agent.color)
            const Icon = agent.icon
            return (
              <div
                key={agent.id}
                className="flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-all duration-300"
                style={{
                  borderColor: active || status === 'ESPERA' ? color : 'hsl(var(--border))',
                  background: 'hsl(var(--surface))',
                  boxShadow:
                    active || status === 'ESPERA'
                      ? `0 0 0 1px ${color}, 0 0 22px -8px ${color}`
                      : 'none',
                }}
              >
                <div
                  className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${active ? 'mission-pulse' : ''}`}
                  style={{
                    background: `color-mix(in srgb, ${agent.color} 16%, transparent)`,
                    color: agent.color,
                  }}
                >
                  <Icon className="h-4.5 w-4.5" style={{ width: 18, height: 18 }} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-semibold">{agent.name}</p>
                  <p className="truncate text-[11px] text-muted">{agent.role}</p>
                </div>
                <span
                  className="figures shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                  style={{
                    color,
                    background: `color-mix(in srgb, ${color} 12%, transparent)`,
                  }}
                >
                  {STATUS_LABEL[status]}
                </span>
              </div>
            )
          })}
        </div>

        {/* ── Feed en vivo ── */}
        <div className="flex min-h-[320px] flex-col rounded-xl border border-border bg-surface p-3 shadow-card lg:col-span-3">
          <p className="figures mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
            Actividad · números del libro, coreografía del equipo
          </p>
          <div ref={feedRef} className="flex-1 space-y-1.5 overflow-y-auto pr-1" style={{ maxHeight: 380 }}>
            {feed.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted">
                {ready
                  ? 'Lanza la misión: verás a los cinco agentes trabajar sobre TU empresa.'
                  : 'Cargando los briefs del equipo…'}
              </p>
            ) : (
              feed.map((entry) => {
                const agent = AGENTS.find((a) => a.id === entry.agentId)!
                return (
                  <div key={entry.id} className="mission-feed-in flex gap-2 text-[12.5px] leading-snug">
                    <span className="figures shrink-0 text-[10px] text-muted" style={{ paddingTop: 2 }}>
                      {entry.time}
                    </span>
                    <span
                      className="figures shrink-0 rounded px-1.5 text-[10px] font-bold"
                      style={{
                        color: agent.color,
                        background: `color-mix(in srgb, ${agent.color} 12%, transparent)`,
                        paddingTop: 2,
                        paddingBottom: 2,
                      }}
                    >
                      {entry.type}
                    </span>
                    <span className="text-ink-2">{entry.message}</span>
                  </div>
                )
              })
            )}
          </div>

          {/* ── Compuerta humana ── */}
          {phase === 'awaiting' && cfoBrief ? (
            <div className="mission-feed-in mt-3 rounded-xl border-2 p-3" style={{ borderColor: 'hsl(var(--warn))' }}>
              <p className="figures text-[10px] font-bold uppercase tracking-[0.16em] text-warn">
                Requiere aprobación humana
              </p>
              <p className="mt-1 text-sm font-semibold">
                Activar la cobranza del vencido y publicar el brief semanal
              </p>
              <p className="mt-1 text-[12.5px] text-muted">
                {briefs.collections?.findings[0]} La recomendación del equipo:{' '}
                {briefs.collections?.recommendations[0]}
              </p>
              <div className="mt-2.5 flex gap-2">
                <Button onClick={approve} className="!px-4 !py-1.5 text-sm">
                  Aprobar
                </Button>
                <Button
                  variant="ghost"
                  className="!px-4 !py-1.5 text-sm"
                  onClick={() => {
                    setPhase('complete')
                    setStatuses((current) => ({ ...current, cfo: 'LISTO' }))
                    setFeed((current) => [
                      ...current,
                      {
                        id: entryId.current++,
                        time: stamp(),
                        agentId: 'cfo',
                        type: 'HANDOFF',
                        message: 'Rechazado por el humano. La propuesta no toca los libros — así se ve la gobernanza.',
                      },
                    ])
                  }}
                >
                  Rechazar
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {/* ── Brief ejecutivo final ── */}
      {phase === 'complete' && ready ? (
        <div className="mission-feed-in rounded-xl border border-border bg-surface p-4 shadow-card">
          <p className="figures text-[10px] font-semibold uppercase tracking-[0.16em] text-accent">
            Brief ejecutivo · síntesis del equipo
          </p>
          <div className="mt-3 grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
            {AGENTS.map((agent) => (
              <div key={agent.id} className="rounded-lg bg-surface-2/60 p-3">
                <p className="figures text-[9px] font-bold uppercase tracking-[0.14em]" style={{ color: agent.color }}>
                  {agent.name}
                </p>
                <p className="mt-0.5 text-[12.5px] leading-snug">{briefs[agent.id]?.headline}</p>
              </div>
            ))}
            <div className="rounded-lg border border-dashed border-border p-3">
              <p className="figures text-[9px] font-bold uppercase tracking-[0.14em] text-muted">
                La regla de la casa
              </p>
              <p className="mt-0.5 text-[12.5px] leading-snug text-muted">
                Los agentes leen y proponen. Escribir en los libros siempre pasa por la bandeja de
                Propuestas — y por tu clic.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
