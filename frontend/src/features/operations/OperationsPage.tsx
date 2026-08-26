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
import { TaxSelect } from '@/components/ui/TaxSelect'
import { JournalEntryModal } from '@/components/ui/JournalEntryModal'
import { TableFooter } from '@/components/ui/Pagination'
import { formatDate, formatMoney, today } from '@/lib/format'
import { useAccounts, useCategories, useContacts } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'
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
  const defaultTaxRate = useAuthStore((state) => state.organization?.default_tax_rate ?? '0.16')
  const [searchParams, setSearchParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(searchParams.has('nuevo'))
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [entryFor, setEntryFor] = useState<Operation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    date: today(),
    description: '',
    amount: '',
    category_id: '',
    project_id: '',
    retention_isr: '',
    retention_iva: '',
    contact_id: '',
    financial_account_id: '',
    tax_rate: defaultTaxRate,
    paid: true,
    notes: '',
  })

  // Un filtro nuevo debe volver a la primera página: si no, la lista sale vacía
  // sin explicación cuando el resultado cabe en menos páginas que el offset.
  const [filters, setFiltersState] = useState({ q: '', start: '', end: '', project_id: '' })
  const setFilters = (next: Partial<typeof filters>) => {
    setFiltersState({ ...filters, ...next })
    setOffset(0)
  }
  const hasFilters = Boolean(filters.q || filters.start || filters.end || filters.project_id)
  const retentionTotal = Number(form.retention_isr || 0) + Number(form.retention_iva || 0)

  const { data: accounts } = useAccounts()
  // Sólo los proyectos abiertos: etiquetar contra uno cerrado ensucia el reporte.
  const { data: projects } = useQuery({
    queryKey: ['projects', 'ACTIVE'],
    queryFn: async () =>
      (await api.get<{ items: { id: string; name: string }[] }>('/projects?status=ACTIVE')).data
        .items,
  })
  const { data: categories } = useCategories(config.categoryKind)
  const { data: contacts } = useContacts(config.contactResource)

  const { data, isLoading } = useQuery({
    queryKey: [config.kind, statusFilter, filters, offset],
    queryFn: async () =>
      (
        await api.get<Page<Operation>>(config.endpoint, {
          params: {
            ...(statusFilter ? { status: statusFilter } : {}),
            ...(filters.q ? { q: filters.q } : {}),
            ...(filters.start ? { start: filters.start } : {}),
            ...(filters.end ? { end: filters.end } : {}),
            ...(filters.project_id ? { project_id: filters.project_id } : {}),
            offset,
          },
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

  const accountLabel = useMemo(() => {
    const map = new Map((accounts ?? []).map((account) => [account.id, account.name]))
    // Sin cuenta significa que el dinero todavía no se mueve, no que falte un dato.
    return (id: string | null) => (id ? (map.get(id) ?? '—') : 'Sin pagar')
  }, [accounts])

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
        tax_rate: form.tax_rate,
        category_id: form.category_id,
        status: form.paid ? 'PAID' : 'PENDING',
      }
      if (form.contact_id) payload[config.contactField] = form.contact_id
      if (form.project_id) payload.project_id = form.project_id
      if (form.retention_isr) payload.retention_isr = form.retention_isr
      if (form.retention_iva) payload.retention_iva = form.retention_iva
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
      project_id: '',
      retention_isr: '',
      retention_iva: '',
      contact_id: '',
      financial_account_id: '',
      tax_rate: defaultTaxRate,
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

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <input
            type="search"
            placeholder="Buscar por concepto…"
            value={filters.q}
            onChange={(event) => setFilters({ q: event.target.value })}
            className="w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm sm:w-56"
          />
          <div className="flex items-center gap-1.5 text-xs text-muted">
            <span>Del</span>
            <input
              type="date"
              value={filters.start}
              onChange={(event) => setFilters({ start: event.target.value })}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
            />
            <span>al</span>
            <input
              type="date"
              value={filters.end}
              onChange={(event) => setFilters({ end: event.target.value })}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
            />
          </div>
          {(projects ?? []).length > 0 ? (
            <select
              value={filters.project_id}
              onChange={(event) => setFilters({ project_id: event.target.value })}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
            >
              <option value="">Todos los proyectos</option>
              {(projects ?? []).map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          ) : null}
          {hasFilters ? (
            <button
              type="button"
              onClick={() => {
                setFiltersState({ q: '', start: '', end: '', project_id: '' })
                setOffset(0)
              }}
              className="text-xs text-muted underline hover:text-ink"
            >
              Limpiar filtros
            </button>
          ) : null}
        </div>
      </PageHeader>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        hasFilters ? (
          <EmptyState
            title="Nada coincide con lo que buscas"
            message="Prueba con otro concepto o amplía el rango de fechas."
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setFiltersState({ q: '', start: '', end: '', project_id: '' })
                  setOffset(0)
                }}
              >
                Limpiar filtros
              </Button>
            }
          />
        ) : (
          <EmptyState
            title={config.emptyTitle}
            message={config.emptyMessage}
            action={<Button onClick={() => setModalOpen(true)}>{config.newLabel}</Button>}
          />
        )
      ) : (
        <Table
          headers={[
            'Fecha',
            'Concepto',
            config.contactResource === 'customers' ? 'Cliente' : 'Proveedor',
            'Categoría',
            config.kind === 'income' ? 'Entró a' : 'Se pagó con',
            'Estado',
            <span key="m" className="block text-right">
              Monto
            </span>,
            '',
          ]}
          secondary={[3, 4, 5]}
          footer={<TableFooter page={data!} onOffsetChange={setOffset} noun={config.noun} />}
        >
          {items.map((item) => (
            <tr key={item.id} className="hover:bg-surface-2/50">
              <td className="whitespace-nowrap px-4 py-2.5 text-muted">{formatDate(item.date)}</td>
              <td className="px-4 py-2.5 font-medium">
                {item.description}
                {item.deductibility_warning ? (
                  <span
                    className="ml-2 cursor-help rounded-full bg-warn/10 px-1.5 py-0.5 text-[11px] font-medium text-warn"
                    title={item.deductibility_warning}
                  >
                    No deducible
                  </span>
                ) : null}
              </td>
              <td className="px-4 py-2.5 text-muted">
                {contactName(config.contactField === 'customer_id' ? item.customer_id : item.vendor_id)}
              </td>
              <td className="px-4 py-2.5 text-muted">{categoryName(item.category_id)}</td>
              {/* Con qué se movió el dinero: es la pregunta que da origen a ARCA. */}
              <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                {accountLabel(item.financial_account_id)}
              </td>
              <td className="px-4 py-2.5">
                <StatusBadge status={item.status} paidLabel={config.paidLabel} />
              </td>
              <td className="px-4 py-2.5 text-right">
                {/* Sin color: en una lista donde todo es ingreso (o todo gasto), pintar
                    cada cifra no informa. El estado ya lo dice la insignia. */}
                <Money value={item.amount} tone={item.status === 'CANCELLED' ? 'muted' : 'ink'} />
              </td>
              <td className="px-4 py-2.5 text-right">
                <div className="flex justify-end gap-1.5">
                  {item.status === 'PAID' ? (
                    <Button
                      variant="ghost"
                      className="!px-2 !py-1 text-xs"
                      onClick={() => setEntryFor(item)}
                    >
                      Póliza
                    </Button>
                  ) : null}
                {item.status === 'PENDING' ? (
                  <>
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
                  </>
                ) : null}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <JournalEntryModal
        sourceType={config.kind === 'income' ? 'income' : 'expense'}
        sourceId={entryFor?.id ?? null}
        title={`Así lo registró ARCA · ${entryFor?.description ?? ''}`}
        open={entryFor !== null}
        onClose={() => setEntryFor(null)}
      />

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
          <TaxSelect
            total={form.amount}
            rate={form.tax_rate}
            onRateChange={(rate) => setForm({ ...form, tax_rate: rate })}
          />
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
          {config.kind === 'expense' ? (
            <details className="rounded-lg border border-border bg-surface-2/40 px-3 py-2">
              <summary className="cursor-pointer text-sm text-muted">
                ¿Le retienes impuestos al proveedor?
              </summary>
              <p className="mt-2 text-xs text-muted">
                Honorarios y arrendamiento a personas físicas retienen ISR e IVA. Lo retenido no
                se le paga al proveedor: se lo entregas al SAT.
              </p>
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <TextInput
                  label="ISR retenido"
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={form.retention_isr}
                  onChange={(event) => setForm({ ...form, retention_isr: event.target.value })}
                />
                <TextInput
                  label="IVA retenido"
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={form.retention_iva}
                  onChange={(event) => setForm({ ...form, retention_iva: event.target.value })}
                />
              </div>
              {retentionTotal > 0 ? (
                <p className="mt-2 text-xs">
                  Al proveedor le llegan{' '}
                  <span className="figures font-medium">
                    {formatMoney(Math.max(Number(form.amount || 0) - retentionTotal, 0))}
                  </span>{' '}
                  y le debes {formatMoney(retentionTotal)} al SAT.
                </p>
              ) : null}
            </details>
          ) : null}
          {(projects ?? []).length > 0 ? (
            <SelectInput
              label="Proyecto (opcional)"
              placeholder="Sin proyecto"
              options={(projects ?? []).map((project) => ({
                value: project.id,
                label: project.name,
              }))}
              value={form.project_id}
              onChange={(event) => setForm({ ...form, project_id: event.target.value })}
            />
          ) : null}
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
