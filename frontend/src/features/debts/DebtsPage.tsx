/** Página compartida de CxC / CxP: misma mecánica, conceptos explícitos. */

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table, Card } from '@/components/ui/Table'
import { formatDate, formatMoney, today } from '@/lib/format'
import { useAccounts, useCategories, useContacts } from '@/lib/hooks'
import type { Debt, Page } from '@/types/api'

interface Config {
  kind: 'receivables' | 'payables'
  endpoint: string
  payEndpoint: string
  title: string
  description: string
  newLabel: string
  contactResource: 'customers' | 'vendors'
  contactLabel: string
  contactField: 'customer_id' | 'vendor_id'
  categoryKind: 'INCOME' | 'EXPENSE'
  categoryLabel: string
  totalLabel: string
  payAction: string
  payModalTitle: string
  accountLabel: string
  emptyTitle: string
  emptyMessage: string
}

export const RECEIVABLES_CONFIG: Config = {
  kind: 'receivables',
  endpoint: '/receivables',
  payEndpoint: 'collect',
  title: 'Por cobrar',
  description: 'Quién te debe y cuánto.',
  newLabel: 'Nueva cuenta por cobrar',
  contactResource: 'customers',
  contactLabel: 'Cliente',
  contactField: 'customer_id',
  categoryKind: 'INCOME',
  categoryLabel: 'Categoría del ingreso',
  totalLabel: 'Por cobrar',
  payAction: 'Registrar cobro',
  payModalTitle: 'Registrar cobro',
  accountLabel: '¿En qué cuenta recibiste el dinero?',
  emptyTitle: 'Nadie te debe (por ahora)',
  emptyMessage:
    'Cuando vendas a crédito, registra aquí la cuenta por cobrar para dar seguimiento a quién te debe y cuánto.',
}

export const PAYABLES_CONFIG: Config = {
  kind: 'payables',
  endpoint: '/payables',
  payEndpoint: 'pay',
  title: 'Por pagar',
  description: 'A quién le debes y cuánto.',
  newLabel: 'Nueva cuenta por pagar',
  contactResource: 'vendors',
  contactLabel: 'Proveedor',
  contactField: 'vendor_id',
  categoryKind: 'EXPENSE',
  categoryLabel: 'Categoría del gasto',
  totalLabel: 'Por pagar',
  payAction: 'Registrar pago',
  payModalTitle: 'Registrar pago',
  accountLabel: '¿Desde qué cuenta pagaste?',
  emptyTitle: 'No debes nada (por ahora)',
  emptyMessage:
    'Cuando compres a crédito, registra aquí la cuenta por pagar para no perder de vista tus compromisos.',
}

const STATUS_FILTERS = [
  { value: '', label: 'Todas' },
  { value: 'OPEN', label: 'Abiertas' },
  { value: 'OVERDUE', label: 'Vencidas' },
  { value: 'PAID', label: 'Pagadas' },
  { value: 'CANCELLED', label: 'Canceladas' },
]

function DebtStatusBadge({ debt }: { debt: Debt }) {
  const map: Record<string, { label: string; className: string }> = {
    OPEN: { label: 'Abierta', className: 'bg-accent-soft text-accent' },
    PARTIAL: { label: 'Parcial', className: 'bg-warn/10 text-warn' },
    OVERDUE: { label: 'Vencida', className: 'bg-neg/10 text-neg' },
    PAID: { label: 'Liquidada', className: 'bg-pos/10 text-pos' },
    CANCELLED: { label: 'Cancelada', className: 'bg-muted/10 text-muted' },
  }
  const config = map[debt.display_status] ?? map.OPEN
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  )
}

export function DebtsPage({ config }: { config: Config }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(searchParams.has('nueva'))
  const [payTarget, setPayTarget] = useState<Debt | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [payError, setPayError] = useState<string | null>(null)
  const [form, setForm] = useState({
    contact_id: '',
    description: '',
    amount: '',
    due_date: '',
    category_id: '',
    notes: '',
  })
  const [payForm, setPayForm] = useState({ amount: '', financial_account_id: '', date: today() })

  const { data: accounts } = useAccounts()
  const { data: categories } = useCategories(config.categoryKind)
  const { data: contacts } = useContacts(config.contactResource)

  const { data, isLoading } = useQuery({
    queryKey: [config.kind, statusFilter],
    queryFn: async () =>
      (
        await api.get<Page<Debt>>(config.endpoint, {
          params: statusFilter ? { status: statusFilter } : {},
        })
      ).data,
  })

  const contactName = useMemo(() => {
    const map = new Map((contacts ?? []).map((contact) => [contact.id, contact.name]))
    return (debt: Debt) => map.get(debt.customer_id ?? debt.vendor_id ?? '') ?? '—'
  }, [contacts])

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: [config.kind] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        [config.contactField]: form.contact_id,
        description: form.description,
        amount: form.amount,
        due_date: form.due_date,
        category_id: form.category_id,
      }
      if (form.notes) payload.notes = form.notes
      await api.post(config.endpoint, payload)
    },
    onSuccess: () => {
      invalidate()
      closeModal()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const payMutation = useMutation({
    mutationFn: async () => {
      if (!payTarget) return
      await api.post(`${config.endpoint}/${payTarget.id}/${config.payEndpoint}`, payForm)
    },
    onSuccess: () => {
      invalidate()
      closePayModal()
    },
    onError: (err) => setPayError(errorMessage(err)),
  })

  const cancelMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.post(`${config.endpoint}/${id}/cancel`, {})
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  function closeModal() {
    setModalOpen(false)
    setError(null)
    setForm({ contact_id: '', description: '', amount: '', due_date: '', category_id: '', notes: '' })
    if (searchParams.has('nueva')) {
      searchParams.delete('nueva')
      setSearchParams(searchParams, { replace: true })
    }
  }

  function openPayModal(debt: Debt) {
    setPayTarget(debt)
    setPayForm({
      amount: debt.balance,
      financial_account_id: accounts?.length === 1 ? accounts[0].id : '',
      date: today(),
    })
  }

  function closePayModal() {
    setPayTarget(null)
    setPayError(null)
  }

  const items = data?.items ?? []
  const openItems = items.filter((debt) => ['OPEN', 'PARTIAL', 'OVERDUE'].includes(debt.display_status))
  const totalOutstanding = openItems.reduce((sum, debt) => sum + Number(debt.balance), 0)
  const totalOverdue = openItems
    .filter((debt) => debt.is_overdue)
    .reduce((sum, debt) => sum + Number(debt.balance), 0)

  return (
    <div>
      <PageHeader
        title={config.title}
        description={config.description}
        actions={<Button onClick={() => setModalOpen(true)}>+ {config.newLabel}</Button>}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-2">
            {STATUS_FILTERS.map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => setStatusFilter(filter.value)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  statusFilter === filter.value
                    ? 'bg-accent text-white'
                    : 'border border-border bg-surface text-muted hover:text-ink'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>
      </PageHeader>

      {statusFilter === '' && items.length > 0 ? (
        <div className="mb-4 grid grid-cols-2 gap-4 sm:max-w-md">
          <Card>
            <div className="text-xs font-medium uppercase tracking-wide text-muted">{config.totalLabel}</div>
            <div className="mt-1.5">
              <Money value={totalOutstanding} size="lg" />
            </div>
          </Card>
          <Card>
            <div className="text-xs font-medium uppercase tracking-wide text-muted">Vencido</div>
            <div className="mt-1.5">
              <Money value={totalOverdue} size="lg" tone={totalOverdue > 0 ? 'neg' : 'ink'} />
            </div>
          </Card>
        </div>
      ) : null}

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        <EmptyState
          title={config.emptyTitle}
          message={config.emptyMessage}
          action={<Button onClick={() => setModalOpen(true)}>{config.newLabel}</Button>}
        />
      ) : (
        <Table
          headers={[
            config.contactLabel,
            'Concepto',
            'Vence',
            'Estado',
            <span key="p" className="block text-right">Pagado / Total</span>,
            <span key="s" className="block text-right">Saldo</span>,
            '',
          ]}
        >
          {items.map((debt) => (
            <tr key={debt.id} className="hover:bg-surface-2/50">
              <td className="px-4 py-2.5 font-medium">{contactName(debt)}</td>
              <td className="px-4 py-2.5">{debt.description}</td>
              <td className={`whitespace-nowrap px-4 py-2.5 ${debt.is_overdue ? 'font-medium text-neg' : 'text-muted'}`}>
                {formatDate(debt.due_date)}
              </td>
              <td className="px-4 py-2.5">
                <DebtStatusBadge debt={debt} />
              </td>
              <td className="figures whitespace-nowrap px-4 py-2.5 text-right text-muted">
                {formatMoney(debt.amount_paid)} / {formatMoney(debt.amount)}
              </td>
              <td className="px-4 py-2.5 text-right">
                <Money value={debt.balance} tone={debt.display_status === 'CANCELLED' ? 'muted' : 'ink'} />
              </td>
              <td className="px-4 py-2.5 text-right">
                {['OPEN', 'PARTIAL', 'OVERDUE'].includes(debt.display_status) ? (
                  <div className="flex justify-end gap-1.5">
                    <Button variant="secondary" className="!px-2.5 !py-1 text-xs" onClick={() => openPayModal(debt)}>
                      {config.payAction}
                    </Button>
                    {Number(debt.amount_paid) === 0 ? (
                      <Button
                        variant="ghost"
                        className="!px-2 !py-1 text-xs"
                        onClick={() => {
                          if (window.confirm('¿Cancelar esta cuenta? Se revertirá su registro contable.'))
                            cancelMutation.mutate(debt.id)
                        }}
                      >
                        Cancelar
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal title={config.newLabel} open={modalOpen} onClose={closeModal}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            setError(null)
            createMutation.mutate()
          }}
          className="space-y-4"
        >
          <SelectInput
            label={config.contactLabel}
            required
            placeholder="Elige uno"
            options={(contacts ?? []).map((contact) => ({ value: contact.id, label: contact.name }))}
            value={form.contact_id}
            onChange={(event) => setForm({ ...form, contact_id: event.target.value })}
          />
          <TextInput
            label="Concepto"
            required
            placeholder={config.kind === 'receivables' ? 'Factura 001 — venta a crédito' : 'Factura del proveedor'}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Monto"
              type="number"
              min="0.01"
              step="0.01"
              required
              placeholder="0.00"
              value={form.amount}
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
            />
            <TextInput
              label="Fecha de vencimiento"
              type="date"
              required
              value={form.due_date}
              onChange={(event) => setForm({ ...form, due_date: event.target.value })}
            />
          </div>
          <SelectInput
            label={config.categoryLabel}
            required
            placeholder="Elige una"
            options={(categories ?? []).map((category) => ({ value: category.id, label: category.name }))}
            value={form.category_id}
            onChange={(event) => setForm({ ...form, category_id: event.target.value })}
          />
          <TextInput
            label="Notas"
            placeholder="Opcional"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={closeModal}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Guardando…' : 'Guardar'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal title={config.payModalTitle} open={payTarget !== null} onClose={closePayModal}>
        {payTarget ? (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              setPayError(null)
              payMutation.mutate()
            }}
            className="space-y-4"
          >
            <p className="text-sm text-muted">
              {contactName(payTarget)} — {payTarget.description}. Saldo pendiente:{' '}
              <span className="figures font-medium text-ink">{formatMoney(payTarget.balance)}</span>
            </p>
            <div className="grid grid-cols-2 gap-4">
              <TextInput
                label="Monto"
                type="number"
                min="0.01"
                step="0.01"
                required
                value={payForm.amount}
                onChange={(event) => setPayForm({ ...payForm, amount: event.target.value })}
              />
              <TextInput
                label="Fecha"
                type="date"
                required
                value={payForm.date}
                onChange={(event) => setPayForm({ ...payForm, date: event.target.value })}
              />
            </div>
            <SelectInput
              label={config.accountLabel}
              required
              placeholder="Elige la cuenta"
              options={(accounts ?? [])
                .filter((account) => account.active)
                .map((account) => ({ value: account.id, label: account.name }))}
              value={payForm.financial_account_id}
              onChange={(event) => setPayForm({ ...payForm, financial_account_id: event.target.value })}
            />
            {payError ? <p className="text-sm text-neg">{payError}</p> : null}
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={closePayModal}>
                Cancelar
              </Button>
              <Button type="submit" disabled={payMutation.isPending}>
                {payMutation.isPending ? 'Registrando…' : config.payAction}
              </Button>
            </div>
          </form>
        ) : null}
      </Modal>
    </div>
  )
}
