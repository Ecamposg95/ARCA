import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, MessageSquarePlus, PanelLeft, Send, Sparkles, Trash2, X } from 'lucide-react'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { useActiveRole } from '@/lib/companies'
import { formatDate } from '@/lib/format'
import { LightMarkdown } from '@/features/assistant/LightMarkdown'
import type {
  AssistantAction,
  AssistantConversation,
  AssistantConversationLite,
  AssistantMessage,
  AssistantStatus,
  Page,
} from '@/types/api'

const EXAMPLES = [
  '¿Cuánto dinero tengo disponible?',
  '¿Qué pagos vencen esta semana?',
  'Registra un gasto de $1,200 de papelería pagado de caja',
]

const WRITE_ROLES = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'MEMBER']

const KIND_LABELS: Record<string, string> = {
  INCOME: 'Ingreso',
  EXPENSE: 'Gasto',
  RECEIVABLE: 'Cuenta por cobrar',
  PAYABLE: 'Cuenta por pagar',
}

const UNAVAILABLE_COPY: Record<string, string> = {
  sin_llave: 'El asistente se activa cuando se conecte la llave de Claude.',
  deshabilitado: 'El asistente está desactivado en esta empresa. El dueño puede encenderlo en Configuración.',
  sin_presupuesto: 'Se agotó el presupuesto del asistente de este mes. Pídele a Atlas que lo amplíe.',
}

export function useAssistantStatus() {
  return useQuery({
    queryKey: ['assistant-status'],
    queryFn: async () => (await api.get<AssistantStatus>('/assistant/status')).data,
    staleTime: 60_000,
  })
}

export function AssistantPage() {
  const queryClient = useQueryClient()
  const role = useActiveRole()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('c')
  const [draft, setDraft] = useState('')
  const [pendingText, setPendingText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const status = useAssistantStatus()
  const conversations = useQuery({
    queryKey: ['assistant-conversations'],
    queryFn: async () =>
      (await api.get<Page<AssistantConversationLite>>('/assistant/conversations', { params: { limit: 100 } })).data,
  })
  const conversation = useQuery({
    queryKey: ['assistant-conversation', selectedId],
    queryFn: async () => (await api.get<AssistantConversation>(`/assistant/conversations/${selectedId}`)).data,
    enabled: selectedId !== null,
    // Si otro envío quedó en curso (otra pestaña), la vista se pone al día sola.
    refetchInterval: (query) => (query.state.data?.busy ? 3_000 : false),
  })

  function select(id: string | null) {
    setSearchParams(id ? { c: id } : {}, { replace: true })
    setDrawerOpen(false)
    setError(null)
  }

  function invalidateAfterTurn() {
    void queryClient.invalidateQueries({ queryKey: ['assistant-conversations'] })
    void queryClient.invalidateQueries({ queryKey: ['assistant-status'] })
    void queryClient.invalidateQueries({ queryKey: ['proposals'] })
    void queryClient.invalidateQueries({ queryKey: ['proposals-count'] })
  }

  const sendMutation = useMutation({
    mutationFn: async (text: string) => {
      let id = selectedId
      if (!id) {
        id = (await api.post<AssistantConversationLite>('/assistant/conversations')).data.id
        select(id)
      }
      await api.post<AssistantMessage>(`/assistant/conversations/${id}/messages`, { text })
      return id
    },
    onMutate: (text) => {
      setPendingText(text)
      setError(null)
    },
    onSuccess: (id) => {
      void queryClient.invalidateQueries({ queryKey: ['assistant-conversation', id] })
      invalidateAfterTurn()
    },
    onError: (err) => setError(errorMessage(err)),
    onSettled: () => setPendingText(null),
  })

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/assistant/conversations/${id}`)
    },
    onSuccess: (_data, id) => {
      if (id === selectedId) select(null)
      void queryClient.invalidateQueries({ queryKey: ['assistant-conversations'] })
    },
    onError: (err) => window.alert(errorMessage(err)),
  })

  const resolveMutation = useMutation({
    mutationFn: async ({ id, approve }: { id: string; approve: boolean }) =>
      (await api.post<AssistantAction>(`/assistant/actions/${id}/${approve ? 'approve' : 'reject'}`)).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['assistant-conversation', selectedId] })
      invalidateAfterTurn()
      for (const key of ['dashboard', 'accounts', 'income', 'expense', 'receivables', 'payables']) {
        void queryClient.invalidateQueries({ queryKey: [key] })
      }
    },
    onError: (err) => window.alert(errorMessage(err)),
  })

  const messages = conversation.data?.messages ?? []
  const busy = sendMutation.isPending || (conversation.data?.busy ?? false)
  const available = status.data?.available ?? false
  const unavailableCopy = status.data && !status.data.available ? UNAVAILABLE_COPY[status.data.reason ?? ''] : null

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, pendingText])

  function send(text: string) {
    const clean = text.trim()
    if (!clean || busy || !available) return
    setDraft('')
    sendMutation.mutate(clean)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send(draft)
    }
  }

  const list = (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3">
        <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">Conversaciones</span>
        <button
          type="button"
          onClick={() => select(null)}
          className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent-soft"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          Nueva
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {(conversations.data?.items ?? []).length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted">Aquí quedarán tus conversaciones.</p>
        ) : null}
        {(conversations.data?.items ?? []).map((item) => (
          <div
            key={item.id}
            className={`group mb-0.5 flex items-center gap-1 rounded-lg transition-colors ${
              item.id === selectedId ? 'bg-accent-soft text-accent' : 'hover:bg-surface-2'
            }`}
          >
            <button
              type="button"
              onClick={() => select(item.id)}
              className="min-w-0 flex-1 px-2.5 py-2 text-left"
            >
              <div className="truncate text-sm">{item.title ?? 'Sin título'}</div>
              <div className="figures text-[10px] text-muted">{formatDate(item.updated_at)}</div>
            </button>
            <button
              type="button"
              aria-label="Borrar conversación"
              onClick={() => {
                if (window.confirm('¿Borrar esta conversación?')) deleteMutation.mutate(item.id)
              }}
              className="mr-1 rounded p-1 text-muted opacity-0 transition-opacity hover:text-neg group-hover:opacity-100"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )

  return (
    <div className="-my-6 flex h-[calc(100vh-7.5rem)] flex-col sm:-my-8 sm:h-[calc(100vh-8.5rem)]">
      <div className="flex items-center justify-between gap-3 border-b border-border py-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Ver conversaciones"
            className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink lg:hidden"
          >
            <PanelLeft className="h-5 w-5" />
          </button>
          <Sparkles className="h-5 w-5 shrink-0 text-accent" />
          <div className="min-w-0">
            <h1 className="font-display text-lg font-semibold leading-tight tracking-tight">Asistente</h1>
            <p className="truncate text-xs text-muted">
              Pregunta por tu negocio en tus palabras. Nada se registra sin tu aprobación.
            </p>
          </div>
        </div>
        {status.data ? (
          <span className="figures hidden shrink-0 text-[11px] text-muted sm:inline">
            {status.data.model_name} · ${Number(status.data.spent_usd).toFixed(2)} de $
            {Number(status.data.budget_usd).toFixed(2)} USD este mes
          </span>
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-border lg:block">{list}</aside>

        {drawerOpen ? (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/50" onClick={() => setDrawerOpen(false)} aria-hidden />
            <div className="absolute inset-y-0 left-0 w-72 bg-surface shadow-float">
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Cerrar"
                className="absolute right-2 top-2 rounded p-1 text-muted hover:text-ink"
              >
                <X className="h-4 w-4" />
              </button>
              {list}
            </div>
          </div>
        ) : null}

        <section className="flex min-w-0 flex-1 flex-col">
          {unavailableCopy ? (
            <div className="mx-4 mt-4 rounded-lg border border-warn/40 bg-warn/10 px-4 py-2.5 text-sm">
              {unavailableCopy}
            </div>
          ) : null}

          <div className="flex-1 overflow-y-auto px-4 py-5">
            {selectedId && conversation.isLoading ? (
              <div className="h-32 animate-pulse rounded-xl bg-surface-2" />
            ) : messages.length === 0 && !pendingText ? (
              <EmptyThread onPick={(text) => send(text)} disabled={!available || busy} />
            ) : (
              <div className="mx-auto max-w-3xl space-y-4">
                {messages.map((message) => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    canResolve={role !== null && WRITE_ROLES.includes(role)}
                    resolving={resolveMutation.isPending}
                    onResolve={(id, approve) => resolveMutation.mutate({ id, approve })}
                  />
                ))}
                {pendingText ? (
                  <>
                    <UserBubble text={pendingText} />
                    <div className="flex items-center gap-2 text-sm text-muted">
                      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" />
                      pensando…
                    </div>
                  </>
                ) : null}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          <div className="border-t border-border px-4 py-3">
            <div className="mx-auto max-w-3xl">
              {error ? <p className="mb-2 text-sm text-neg">{error}</p> : null}
              <div className="flex items-end gap-2 rounded-xl border border-border bg-surface p-2 focus-within:border-accent">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={onKeyDown}
                  disabled={!available || busy}
                  rows={1}
                  placeholder={
                    available ? 'Escribe tu pregunta… (Enter para enviar)' : 'El asistente no está disponible'
                  }
                  className="max-h-40 min-h-[2.25rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted disabled:opacity-60"
                />
                <Button
                  onClick={() => send(draft)}
                  disabled={!available || busy || !draft.trim()}
                  className="!px-3"
                  aria-label="Enviar"
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
              <p className="mt-1.5 text-[11px] text-muted">
                El asistente lee tus números y propone operaciones; tú apruebas cada una. También las ves en{' '}
                <Link to="/propuestas" className="text-accent underline">
                  Propuestas
                </Link>
                .
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function EmptyThread({ onPick, disabled }: { onPick: (text: string) => void; disabled: boolean }) {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center py-10 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft">
        <Sparkles className="h-6 w-6 text-accent" />
      </span>
      <h2 className="font-display mt-4 text-base font-semibold">¿Qué quieres saber de tu negocio?</h2>
      <p className="mt-1.5 text-sm text-muted">
        Pregunta como le preguntarías a tu contador. El asistente consulta tus números reales y, si quieres
        registrar algo, te lo propone para que lo apruebes.
      </p>
      <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={disabled}
            onClick={() => onPick(example)}
            className="rounded-full border border-border bg-surface px-3.5 py-2 text-sm text-ink transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  )
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-accent-soft px-4 py-2.5 text-sm text-ink">
        {text}
      </div>
    </div>
  )
}

function MessageBubble({
  message,
  canResolve,
  resolving,
  onResolve,
}: {
  message: AssistantMessage
  canResolve: boolean
  resolving: boolean
  onResolve: (id: string, approve: boolean) => void
}) {
  if (message.role === 'user') return <UserBubble text={message.text ?? ''} />
  const isNotice = ['budget', 'max_tokens', 'refusal', 'max_iterations'].includes(message.stop_reason ?? '')
  return (
    <div className="flex flex-col items-start gap-2">
      {message.text ? (
        <div
          className={`max-w-[92%] rounded-2xl rounded-bl-sm border px-4 py-3 ${
            isNotice ? 'border-warn/40 bg-warn/10' : 'border-border bg-surface'
          }`}
        >
          <LightMarkdown text={message.text} />
        </div>
      ) : null}
      {message.steps.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1 pl-1 text-[11px] text-muted">
          {message.steps.map((step, index) => (
            <span key={index} className="flex items-center gap-1">
              {index > 0 ? <span aria-hidden>·</span> : null}
              {step.ok ? (
                <Check className="h-3 w-3 text-pos" />
              ) : (
                <X className="h-3 w-3 text-neg" />
              )}
              {step.summary ?? step.name}
            </span>
          ))}
        </div>
      ) : null}
      {message.actions.map((action) => (
        <ActionCard
          key={action.id}
          action={action}
          canResolve={canResolve}
          resolving={resolving}
          onResolve={onResolve}
        />
      ))}
    </div>
  )
}

function ActionCard({
  action,
  canResolve,
  resolving,
  onResolve,
}: {
  action: AssistantAction
  canResolve: boolean
  resolving: boolean
  onResolve: (id: string, approve: boolean) => void
}) {
  const kind = action.proposal_kind ? KIND_LABELS[action.proposal_kind] ?? action.proposal_kind : 'Operación'
  return (
    <div className="w-full max-w-[92%] rounded-xl border border-accent/40 bg-surface p-4 shadow-card">
      <div className="flex items-center gap-2">
        <span className="inline-flex rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
          {kind}
        </span>
        <span className="text-xs text-muted">Propuesta pendiente de tu aprobación</span>
      </div>
      <p className="mt-2 text-sm font-medium">{action.summary}</p>
      <div className="mt-3 flex items-center gap-2">
        {action.status === 'PENDING' ? (
          canResolve ? (
            <>
              <Button disabled={resolving} onClick={() => onResolve(action.id, true)}>
                Aprobar
              </Button>
              <Button variant="secondary" disabled={resolving} onClick={() => onResolve(action.id, false)}>
                Rechazar
              </Button>
            </>
          ) : (
            <span className="text-xs text-muted">Tu rol no permite aprobar; pídeselo a un administrador.</span>
          )
        ) : action.status === 'APPROVED' ? (
          <span className="flex items-center gap-1 text-sm text-pos">
            <Check className="h-4 w-4" /> Aprobada y registrada
          </span>
        ) : (
          <span className="flex items-center gap-1 text-sm text-muted">
            <X className="h-4 w-4" /> Rechazada
          </span>
        )}
      </div>
    </div>
  )
}
