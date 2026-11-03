/** Apertura: los saldos con los que el negocio empezó en ONE Finance, a la fecha de corte.
 *
 *  Todo lo que no se ha confirmado vive contra la cuenta puente (3901) y se
 *  corrige cuando llega el documento. El backend calcula la diferencia, asienta
 *  el ajuste fechado en el corte y deja el motivo en el historial; aquí sólo se
 *  captura la cifra nueva.
 */

import { Fragment, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { HistoryTimeline } from '@/components/ui/HistoryTimeline'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card, Table } from '@/components/ui/Table'
import { formatDate, monthStart } from '@/lib/format'
import { useActiveRole } from '@/lib/companies'
import type { OpeningAccountRow, OpeningOtherRow, OpeningStatus, OpeningSummary } from '@/types/api'

const QUERY_KEY = ['opening']
const ADMIN_ROLES = ['OWNER', 'ADMIN']
const ADJUST_ROLES = ['OWNER', 'ADMIN', 'ACCOUNTANT']

const STATUS_OPTIONS = [
  { value: 'PROVISIONAL', label: 'Provisional' },
  { value: 'CONFIRMED', label: 'Confirmado' },
]

const MONEY_GROUPS: { key: string; title: string; hint?: string; types: OpeningAccountRow['type'][] }[] = [
  { key: 'cash', title: 'Cajas', types: ['CASH'] },
  { key: 'bank', title: 'Bancos', types: ['BANK', 'OTHER'] },
  {
    key: 'processor',
    title: 'Procesador (en tránsito)',
    hint: 'Cobrado con tarjeta que el procesador todavía no deposita.',
    types: ['PROCESSOR'],
  },
  { key: 'card', title: 'Tarjetas', hint: 'Lo que se debía al corte.', types: ['CREDIT_CARD'] },
]

function StatusChip({ status }: { status: OpeningStatus | null }) {
  const confirmed = status === 'CONFIRMED'
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
        confirmed ? 'bg-pos/10 text-pos' : 'bg-warn/10 text-warn'
      }`}
    >
      {confirmed ? 'Confirmado' : 'Provisional'}
    </span>
  )
}

export function OpeningPage() {
  const role = useActiveRole()
  const canAdmin = ADMIN_ROLES.includes(role ?? '')
  const canAdjust = ADJUST_ROLES.includes(role ?? '')
  const [cutoffOpen, setCutoffOpen] = useState(false)
  const [adjusting, setAdjusting] = useState<OpeningAccountRow | null>(null)
  const [other, setOther] = useState<OpeningOtherRow | 'new' | null>(null)
  const [historyOf, setHistoryOf] = useState<string | null>(null)

  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: async () => (await api.get<OpeningSummary>('/opening')).data,
    enabled: canAdjust,
  })

  const header = (
    <PageHeader
      title="Apertura"
      description="Los saldos con los que tu negocio empezó en ONE Finance."
      actions={
        <Link to="/configuracion" className="text-sm text-muted hover:text-ink">
          ← Configuración
        </Link>
      }
    />
  )

  if (!canAdjust) {
    return (
      <div>
        {header}
        <EmptyState
          title="Sólo para quien lleva las cuentas"
          message="La apertura la revisan el dueño, los administradores y el contador."
        />
      </div>
    )
  }
  if (query.isLoading) {
    return (
      <div>
        {header}
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      </div>
    )
  }
  if (query.isError || !query.data) {
    return (
      <div>
        {header}
        <p className="text-sm text-neg">{errorMessage(query.error)}</p>
      </div>
    )
  }

  const summary = query.data
  if (!summary.opening_date) {
    return (
      <div>
        {header}
        <EmptyState
          title="Aún no hay fecha de corte"
          message="Elige el día en que tu negocio empieza en ONE Finance. Todos los saldos de apertura van fechados ahí, y los puedes capturar provisionales y corregirlos después."
          action={
            canAdmin ? (
              <Button onClick={() => setCutoffOpen(true)}>Fijar fecha de corte</Button>
            ) : (
              <p className="text-sm text-muted">Pídele al dueño o a un administrador que la fije.</p>
            )
          }
        />
        <CutoffModal open={cutoffOpen} onClose={() => setCutoffOpen(false)} current={null} />
      </div>
    )
  }

  const toggleHistory = (key: string) => setHistoryOf((current) => (current === key ? null : key))

  return (
    <div>
      {header}
      <CutoffCard summary={summary} canAdmin={canAdmin} onChangeDate={() => setCutoffOpen(true)} />

      {MONEY_GROUPS.map((group) => {
        const rows = summary.accounts.filter((account) => group.types.includes(account.type))
        if (rows.length === 0) return null
        return (
          <Section key={group.key} title={group.title} hint={group.hint}>
            <Table headers={['Cuenta', 'Saldo de apertura', 'Estado', 'Fuente', '']} secondary={[4]}>
              {rows.map((account) => (
                <Fragment key={account.id}>
                  <tr>
                    <td className="px-4 py-3">
                      <span className={account.active ? 'font-medium' : 'font-medium text-muted line-through'}>
                        {account.name}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <Money value={account.opening_balance} size="sm" />
                    </td>
                    <td className="px-4 py-3">
                      <StatusChip status={account.opening_status} />
                    </td>
                    <td className="px-4 py-3 text-muted">{account.opening_note ?? '—'}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => toggleHistory(account.id)}>
                        Historial
                      </Button>
                      <Button
                        variant="secondary"
                        className="ml-1 !px-2.5 !py-1 text-xs"
                        disabled={!account.active}
                        onClick={() => setAdjusting(account)}
                      >
                        Ajustar
                      </Button>
                    </td>
                  </tr>
                  {historyOf === account.id ? (
                    <tr>
                      <td colSpan={5} className="bg-surface-2/40 px-6 py-4">
                        <HistoryTimeline endpoint="/accounts" entityId={account.id} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </Table>
          </Section>
        )
      })}

      {summary.loans.length > 0 ? (
        <Section title="Préstamos" hint="Su saldo al corte se registra desde Patrimonio.">
          <Table headers={['Préstamo', 'Saldo por pagar', 'Desde', '']}>
            {summary.loans.map((loan) => (
              <tr key={loan.id}>
                <td className="px-4 py-3">
                  <span className="font-medium">{loan.lender}</span>
                  <span className="ml-2 text-xs text-muted">{loan.description}</span>
                </td>
                <td className="px-4 py-3">
                  <Money value={loan.outstanding} size="sm" />
                </td>
                <td className="px-4 py-3 text-muted">{formatDate(loan.start_date)}</td>
                <td className="px-4 py-3 text-right">
                  <Link to="/patrimonio" className="text-xs font-medium text-accent hover:underline">
                    Ver en Patrimonio
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        </Section>
      ) : null}

      {summary.fixed_assets.length > 0 ? (
        <Section title="Activo fijo" hint="Su valor al corte se registra desde Patrimonio.">
          <Table headers={['Activo', 'Valor en libros', 'Comprado', '']}>
            {summary.fixed_assets.map((asset) => (
              <tr key={asset.id}>
                <td className="px-4 py-3 font-medium">{asset.name}</td>
                <td className="px-4 py-3">
                  <Money value={asset.book_value} size="sm" />
                </td>
                <td className="px-4 py-3 text-muted">{formatDate(asset.acquisition_date)}</td>
                <td className="px-4 py-3 text-right">
                  <Link to="/patrimonio" className="text-xs font-medium text-accent hover:underline">
                    Ver en Patrimonio
                  </Link>
                </td>
              </tr>
            ))}
          </Table>
        </Section>
      ) : null}

      <Section
        title="Otras cuentas"
        hint="Depósitos en garantía, anticipos, deudores, intereses y lo demás que no lleva un módulo."
        action={
          <Button variant="secondary" className="!px-2.5 !py-1 text-xs" onClick={() => setOther('new')}>
            Agregar cuenta
          </Button>
        }
      >
        {summary.others.length === 0 ? (
          <EmptyState
            title="Sin otras cuentas en la apertura"
            message="Si al corte tenías depósitos, anticipos o deudas que no son bancos ni tarjetas, agrégalos aquí."
            action={<Button onClick={() => setOther('new')}>Agregar cuenta</Button>}
          />
        ) : (
          <Table headers={['Cuenta', 'Saldo de apertura', 'Estado', '']}>
            {summary.others.map((line) => (
              <Fragment key={line.account_id}>
                <tr>
                  <td className="px-4 py-3">
                    <span className="figures mr-2 text-xs text-muted">{line.code}</span>
                    <span className="font-medium">{line.name}</span>
                  </td>
                  <td className="px-4 py-3">
                    <Money value={line.amount} size="sm" />
                  </td>
                  <td className="px-4 py-3">
                    <StatusChip status={summary.opening_status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <Button
                      variant="ghost"
                      className="!px-2 !py-1 text-xs"
                      onClick={() => toggleHistory(`other:${line.account_id}`)}
                    >
                      Historial
                    </Button>
                    <Button variant="secondary" className="ml-1 !px-2.5 !py-1 text-xs" onClick={() => setOther(line)}>
                      Ajustar
                    </Button>
                  </td>
                </tr>
                {historyOf === `other:${line.account_id}` ? (
                  <tr>
                    <td colSpan={4} className="bg-surface-2/40 px-6 py-4">
                      <HistoryTimeline endpoint="/opening" entityId={summary.organization_id} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </Table>
        )}
      </Section>

      <CutoffModal
        open={cutoffOpen}
        onClose={() => setCutoffOpen(false)}
        current={summary.opening_date}
      />
      {adjusting ? (
        <AdjustAccountModal account={adjusting} cutoff={summary.opening_date} onClose={() => setAdjusting(null)} />
      ) : null}
      {other ? <AdjustOtherModal summary={summary} line={other} onClose={() => setOther(null)} /> : null}
    </div>
  )
}

function Section({
  title,
  hint,
  action,
  children,
}: {
  title: string
  hint?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-display text-lg font-semibold">{title}</h2>
          {hint ? <p className="text-sm text-muted">{hint}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function CutoffCard({
  summary,
  canAdmin,
  onChangeDate,
}: {
  summary: OpeningSummary
  canAdmin: boolean
  onChangeDate: () => void
}) {
  const queryClient = useQueryClient()
  const [showHistory, setShowHistory] = useState(false)
  const confirmed = summary.opening_status === 'CONFIRMED'
  const setStatus = useMutation({
    mutationFn: async (status: OpeningStatus) =>
      (await api.patch<OpeningSummary>('/opening', { opening_status: status })).data,
    onSuccess: (saved) => queryClient.setQueryData(QUERY_KEY, saved),
    onError: (err) => window.alert(errorMessage(err)),
  })

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Fecha de corte</p>
          <div className="mt-1 flex items-center gap-3">
            <span className="font-display text-2xl font-semibold">{formatDate(summary.opening_date ?? '')}</span>
            <StatusChip status={summary.opening_status} />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {canAdmin && !confirmed ? (
              <Button onClick={() => setStatus.mutate('CONFIRMED')} disabled={setStatus.isPending}>
                Marcar como confirmada
              </Button>
            ) : null}
            {canAdmin && confirmed ? (
              <Button variant="secondary" onClick={() => setStatus.mutate('PROVISIONAL')} disabled={setStatus.isPending}>
                Volver a provisional
              </Button>
            ) : null}
            {canAdmin ? (
              <Button variant="ghost" onClick={onChangeDate}>
                Cambiar fecha
              </Button>
            ) : null}
            <Button variant="ghost" onClick={() => setShowHistory((value) => !value)}>
              {showHistory ? 'Ocultar historial' : 'Historial de la apertura'}
            </Button>
          </div>
        </div>
        <div className="max-w-xs text-right">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Por identificar</p>
          <div className="mt-1">
            <Money value={summary.bridge_balance} size="lg" />
          </div>
          <p className="mt-1 text-xs text-muted">
            Lo que no se ha confirmado queda en la cuenta puente y se corrige cuando llegue el estado de cuenta.
          </p>
        </div>
      </div>
      {showHistory ? (
        <div className="mt-5 border-t border-border pt-4">
          <HistoryTimeline endpoint="/opening" entityId={summary.organization_id} />
        </div>
      ) : null}
    </Card>
  )
}

function CutoffModal({ open, onClose, current }: { open: boolean; onClose: () => void; current: string | null }) {
  const queryClient = useQueryClient()
  const [date, setDate] = useState(current ?? monthStart())
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: async () => (await api.patch<OpeningSummary>('/opening', { opening_date: date })).data,
    onSuccess: (saved) => {
      queryClient.setQueryData(QUERY_KEY, saved)
      setError(null)
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })
  return (
    <Modal title="Fecha de corte" open={open} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <p className="text-sm text-muted">
          El día en que tu negocio empieza en ONE Finance. Los saldos de apertura y sus correcciones van fechados
          aquí; lo que registres después queda como está.
        </p>
        <TextInput label="Fecha de corte" type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={save.isPending}>
            Guardar
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function AdjustAccountModal({
  account,
  cutoff,
  onClose,
}: {
  account: OpeningAccountRow
  cutoff: string | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({
    target: account.opening_balance,
    reason: '',
    status: account.opening_status as string,
    note: account.opening_note ?? '',
  })
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post(`/accounts/${account.id}/opening-adjustment`, {
          target_opening_balance: form.target.trim() || '0',
          reason: form.reason.trim(),
          status: form.status,
          note: form.note,
        })
      ).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['history'] })
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  return (
    <Modal title={`Ajustar apertura · ${account.name}`} open onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <p className="text-sm text-muted">
          El ajuste va fechado al corte ({cutoff ? formatDate(cutoff) : '—'}). Lo registrado después queda como está y
          el saldo de hoy se mueve sólo por la diferencia.
        </p>
        <TextInput
          label={account.is_liability ? 'Deuda al corte' : 'Saldo al corte'}
          type="number"
          step="0.01"
          min="0"
          inputMode="decimal"
          required
          value={form.target}
          onChange={(e) => setForm({ ...form, target: e.target.value })}
        />
        <TextInput
          label="Motivo"
          required
          minLength={5}
          placeholder="Llegó el estado de cuenta de octubre"
          value={form.reason}
          onChange={(e) => setForm({ ...form, reason: e.target.value })}
        />
        <div className="grid grid-cols-2 gap-3">
          <SelectInput
            label="Estado"
            options={STATUS_OPTIONS}
            value={form.status}
            onChange={(e) => setForm({ ...form, status: e.target.value })}
          />
          <TextInput
            label="Fuente (opcional)"
            placeholder="Estado de cuenta oct-2026"
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
          />
        </div>
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={save.isPending}>
            Guardar ajuste
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function AdjustOtherModal({
  summary,
  line,
  onClose,
}: {
  summary: OpeningSummary
  line: OpeningOtherRow | 'new'
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const balancing = summary.other_balancing_code ?? '3901'
  const present = new Set(summary.others.map((item) => item.account_id))
  const candidates = summary.other_candidates.filter(
    (candidate) => !present.has(candidate.account_id) && candidate.code !== balancing,
  )
  const [form, setForm] = useState({
    account_id: line === 'new' ? '' : line.account_id,
    amount: line === 'new' ? '' : line.amount,
    reason: '',
  })
  const [error, setError] = useState<string | null>(null)
  const save = useMutation({
    mutationFn: async () => {
      // La apertura se reemplaza completa: las demás cuentas viajan como están.
      const lines = summary.others
        .filter((item) => item.account_id !== form.account_id)
        .map((item) => ({ account_id: item.account_id, amount: item.amount }))
      lines.push({ account_id: form.account_id, amount: form.amount.trim() || '0' })
      return (
        await api.put('/accounting/opening-balance', {
          reason: form.reason.trim(),
          balancing_code: balancing,
          lines,
        })
      ).data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEY })
      void queryClient.invalidateQueries({ queryKey: ['history'] })
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  return (
    <Modal title={line === 'new' ? 'Agregar cuenta a la apertura' : `Ajustar apertura · ${line.name}`} open onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event: FormEvent) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <p className="text-sm text-muted">
          Se revierte la apertura vigente y se asienta la nueva al corte, en un solo paso. En cero, la cuenta sale de
          la apertura.
        </p>
        {line === 'new' ? (
          <SelectInput
            label="Cuenta"
            required
            placeholder="Elige una cuenta"
            options={candidates.map((candidate) => ({
              value: candidate.account_id,
              label: `${candidate.code} · ${candidate.name}`,
            }))}
            value={form.account_id}
            onChange={(e) => setForm({ ...form, account_id: e.target.value })}
          />
        ) : null}
        <TextInput
          label="Saldo al corte"
          type="number"
          step="0.01"
          min="0"
          inputMode="decimal"
          required
          value={form.amount}
          onChange={(e) => setForm({ ...form, amount: e.target.value })}
        />
        <TextInput
          label="Motivo"
          required
          minLength={5}
          placeholder="Contrato de arrendamiento: depósito en garantía"
          value={form.reason}
          onChange={(e) => setForm({ ...form, reason: e.target.value })}
        />
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={save.isPending || !form.account_id}>
            Guardar ajuste
          </Button>
        </div>
      </form>
    </Modal>
  )
}
