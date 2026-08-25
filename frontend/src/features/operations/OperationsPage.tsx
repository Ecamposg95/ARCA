/** Página compartida de Ingresos / Gastos: misma mecánica, conceptos explícitos. */

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
import { StatusBadge } from '@/components/ui/StatusBadge'
import { Table } from '@/components/ui/Table'
import { TableFooter } from '@/components/ui/Pagination'
import { formatDate, today } from '@/lib/format'
import { useAccounts, useCategories, useContacts } from '@/lib/hooks'
import type { Expense, Income, Page } from '@/types/api'

type Operation = Income & Expense

interface Config {
  kind: 'income' | 'expense'
  endpoint: string
  title: string
  description: string
  newLabel: string
  contactResource: 'customers' | 'vendors'
  contactLabel: string
  contactField: 'customer_id' | 'vendor_id'
  categoryKind: 'INCOME' | 'EXPENSE'
  accountLabel: string
  paidLabel: string
  payAction: string
  emptyTitle: string
  emptyMessage: string
  /** Plural para el pie de tabla: "ingresos" | "gastos" */
  noun: string
}

export const INCOME_CONFIG: Config = {
  kind: 'income',
  endpoint: '/income',
  title: 'Ingresos',
  description: 'Lo que vendes y lo que te pagan.',
  newLabel: 'Nuevo ingreso',
  contactResource: 'customers',
  contactLabel: 'Cliente (opcional)',
  contactField: 'customer_id',
  categoryKind: 'INCOME',
  accountLabel: '¿En qué cuenta recibiste el dinero?',
  paidLabel: 'Cobrado',
  payAction: 'Registrar cobro',
  emptyTitle: 'Aún no tienes ingresos',
  emptyMessage:
    'Registra tu primera venta o ingreso para comenzar a entender cómo se mueve tu negocio.',
  noun: 'ingresos',
}

export const EXPENSE_CONFIG: Config = {
  kind: 'expense',
  endpoint: '/expenses',
  title: 'Gastos',
  description: 'Lo que compras y lo que pagas.',
  newLabel: 'Nuevo gasto',
  contactResource: 'vendors',
  contactLabel: 'Proveedor (opcional)',
  contactField: 'vendor_id',
  categoryKind: 'EXPENSE',
  accountLabel: '¿Desde qué cuenta pagaste?',
  paidLabel: 'Pagado',
  payAction: 'Registrar pago',
  emptyTitle: 'Aún no tienes gastos',
  emptyMessage: 'Registra tu primer gasto para saber a dónde se va el dinero.',
  noun: 'gastos',
}

export function OperationsPage({ config }: { config: Config }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(searchParams.has('nuevo'))
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    date: today(),
    description: '',
    amount: '',
    category_id: '',
    contact_id: '',
    financial_account_id: '',
    paid: true,
    notes: '',
  })

  const { data: accounts } = useAccounts()
  const { data: categories } = useCategories(config.categoryKind)
  const { data: contacts } = useContacts(config.contactResource)

  const { data, isLoading } = useQuery({
    queryKey: [config.kind, statusFilter, offset],
    queryFn: async () =>
      (
        await api.get<Page<Operation>>(config.endpoint, {
          params: { ...(statusFilter ? { status: statusFilter } : {}), offset },
        })
      ).data,
  })

  const categoryName = useMemo(() => {
    const map = new Map((categories ?? []).map((category) => [category.id, category.name]))
    return (id: string) => map.get(id) ?? '—'
  }, [categories])

  const contactName = useMemo(() => {
    const map = new Map((contacts ?? []).map((contact) => [contact.id, contact.name]))
    return (id: string | null) => (id ? (map.get(id) ?? '—') : '—')
  }, [contacts])

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: [config.kind] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        date: form.date,
        description: form.description,
        amount: form.amount,
        category_id: form.category_id,
        status: form.paid ? 'PAID' : 'PENDING',
      }
      if (form.contact_id) payload[config.contactField] = form.contact_id
      if (form.financial_account_id) payload.financial_account_id = form.financial_account_id
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
    mutationFn: async ({ id, accountId }: { id: string; accountId: string }) => {
      await api.post(`${config.endpoint}/${id}/pay`, { financial_account_id: accountId })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
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
    setForm({
      date: today(),
      description: '',
      amount: '',
      category_id: '',
      contact_id: '',
      financial_account_id: '',
      paid: true,
      notes: '',
    })
    if (searchParams.has('nuevo')) {
      searchParams.delete('nuevo')
      setSearchParams(searchParams, { replace: true })
    }
  }

  const items = data?.items ?? []

  return (
    <div>
      <PageHeader
        title={config.title}
        description={config.description}
        actions={<Button onClick={() => setModalOpen(true)}>+ {config.newLabel}</Button>}
      >
        <div className="flex gap-2">
          {['', 'PENDING', 'PAID', 'CANCELLED'].map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => {
                setStatusFilter(status)
                setOffset(0)
              }}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                statusFilter === status
                  ? 'bg-accent text-on-accent'
                  : 'bg-surface text-muted hover:text-ink border border-border'
              }`}
            >
              {status === ''
                ? 'Todos'
                : status === 'PENDING'
                  ? 'Pendientes'
                  : status === 'PAID'
                    ? config.paidLabel + 's'
                    : 'Cancelados'}
            </button>
          ))}
        </div>
      </PageHeader>

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
            'Fecha',
            'Concepto',
            config.contactResource === 'customers' ? 'Cliente' : 'Proveedor',
            'Categoría',
            'Estado',
            <span key="m" className="block text-right">
              Monto
            </span>,
            '',
          ]}
          footer={<TableFooter page={data!} onOffsetChange={setOffset} noun={config.noun} />}
        >
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-surface-2/50">
              <td className="whitespace-nowrap px-4 py-2.5 text-muted">{formatDate(item.date)}</td>
              <td className="px-4 py-2.5 font-medium">{item.description}</td>
              <td className="px-4 py-2.5 text-muted">
                {contactName(config.contactField === 'customer_id' ? item.customer_id : item.vendor_id)}
              </td>
              <td className="px-4 py-2.5 text-muted">{categoryName(item.category_id)}</td>
              <td className="px-4 py-2.5">
                <StatusBadge status={item.status} paidLabel={config.paidLabel} />
              </td>
              <td className="px-4 py-2.5 text-right">
                {/* Sin color: en una lista donde todo es ingreso (o todo gasto), pintar
                    cada cifra no informa. El estado ya lo dice la insignia. */}
                <Money value={item.amount} tone={item.status === 'CANCELLED' ? 'muted' : 'ink'} />
              </td>
              <td className="px-4 py-2.5 text-right">
                {item.status === 'PENDING' ? (
                  <div className="flex justify-end gap-1.5">
                    <Button
                      variant="secondary"
                      className="!px-2.5 !py-1 text-xs"
                      onClick={() => {
                        const accountId =
                          item.financial_account_id || (accounts?.length === 1 ? accounts[0].id : '')
                        if (!accountId) {
                          window.alert('Primero elige la cuenta: edita la operación o crea una cuenta de dinero.')
                          return
                        }
                        payMutation.mutate({ id: item.id, accountId })
                      }}
                    >
                      {config.payAction}
                    </Button>
                    <Button
                      variant="ghost"
                      className="!px-2 !py-1 text-xs"
                      onClick={() => {
                        if (window.confirm('¿Cancelar esta operación?')) cancelMutation.mutate(item.id)
                      }}
                    >
                      Cancelar
                    </Button>
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
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Fecha"
              type="date"
              required
              value={form.date}
              onChange={(event) => setForm({ ...form, date: event.target.value })}
            />
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
          </div>
          <TextInput
            label="Concepto"
            required
            placeholder={config.kind === 'income' ? 'Venta de mostrador' : 'Renta del local'}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-4">
            <SelectInput
              label="Categoría"
              required
              placeholder="Elige una"
              options={(categories ?? []).map((category) => ({ value: category.id, label: category.name }))}
              value={form.category_id}
              onChange={(event) => setForm({ ...form, category_id: event.target.value })}
            />
            <SelectInput
              label={config.contactLabel}
              placeholder="Sin asignar"
              options={(contacts ?? []).map((contact) => ({ value: contact.id, label: contact.name }))}
              value={form.contact_id}
              onChange={(event) => setForm({ ...form, contact_id: event.target.value })}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.paid}
              onChange={(event) => setForm({ ...form, paid: event.target.checked })}
              className="h-4 w-4 accent-[hsl(var(--accent))]"
            />
            {config.kind === 'income' ? 'Ya me pagaron' : 'Ya lo pagué'}
          </label>
          {form.paid ? (
            <SelectInput
              label={config.accountLabel}
              required
              placeholder="Elige la cuenta"
              options={(accounts ?? [])
                .filter((account) => account.active)
                .map((account) => ({ value: account.id, label: account.name }))}
              value={form.financial_account_id}
              onChange={(event) => setForm({ ...form, financial_account_id: event.target.value })}
            />
          ) : null}
          <TextInput
            label="Notas (opcional)"
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
    </div>
  )
}
