import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { handlePendingApproval } from '@/lib/approvals'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table } from '@/components/ui/Table'
import { TableFooter } from '@/components/ui/Pagination'
import {
  DimensionChips,
  DimensionFilterSelects,
  dimensionParams,
  type DimensionValues,
} from '@/components/ui/DimensionFields'
import {
  DownloadExcelButton,
  FineFilterChips,
  FineFilterSelects,
  countFineFilters,
  fineFilterParams,
  type FineFilterValues,
} from '@/components/ui/ListFilters'
import { FilterChip, FilterToggle } from '@/components/ui/TableTools'
import { formatDate, formatMoney, today } from '@/lib/format'
import { useAccounts, useCategories, useDimensions } from '@/lib/hooks'
import type { Page, Transaction } from '@/types/api'

const TYPE_LABELS: Record<string, { label: string; inflow: boolean }> = {
  INCOME: { label: 'Ingreso', inflow: true },
  EXPENSE: { label: 'Gasto', inflow: false },
  TRANSFER_IN: { label: 'Traspaso (entrada)', inflow: true },
  TRANSFER_OUT: { label: 'Traspaso (salida)', inflow: false },
  RECEIVABLE_COLLECTION: { label: 'Cobro', inflow: true },
  PAYABLE_PAYMENT: { label: 'Pago', inflow: false },
  ADJUSTMENT: { label: 'Ajuste', inflow: false },
  REVERSAL_IN: { label: 'Reverso (entrada)', inflow: true },
  REVERSAL_OUT: { label: 'Reverso (salida)', inflow: false },
}

/** Filtros que viven en la URL (nombre del parámetro en español, como `cuenta`):
 *  "lo que se pagó en efectivo en octubre desde BBVA" se comparte con un enlace. */
const URL_FILTERS = {
  q: 'q',
  start: 'desde',
  end: 'hasta',
  transaction_type: 'tipo',
  status: 'estado',
  category_id: 'categoria',
  payment_method: 'forma',
  created_by: 'registro',
  min_amount: 'min',
  max_amount: 'max',
} as const
type UrlFilterKey = keyof typeof URL_FILTERS
type UrlFilters = Record<UrlFilterKey, string>

export function TransactionsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [transferOpen, setTransferOpen] = useState(searchParams.has('transferir'))
  // La cuenta vive en la URL: se puede compartir "los movimientos de BBVA".
  const accountFilter = searchParams.get('cuenta') ?? ''
  const setAccountFilter = (value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set('cuenta', value)
    else next.delete('cuenta')
    setSearchParams(next, { replace: true })
  }
  // Unidad y contribuyente también en la URL: "los movimientos de Morelos" se comparten.
  const dimensions: DimensionValues = {
    business_unit_id: searchParams.get('unidad') ?? '',
    fiscal_entity_id: searchParams.get('contribuyente') ?? '',
  }
  const setDimensions = (next: Partial<DimensionValues>) => {
    const merged = { ...dimensions, ...next }
    const params = new URLSearchParams(searchParams)
    if (merged.business_unit_id) params.set('unidad', merged.business_unit_id)
    else params.delete('unidad')
    if (merged.fiscal_entity_id) params.set('contribuyente', merged.fiscal_entity_id)
    else params.delete('contribuyente')
    setSearchParams(params, { replace: true })
    setOffset(0)
  }
  const urlFilters = Object.fromEntries(
    (Object.keys(URL_FILTERS) as UrlFilterKey[]).map((key) => [
      key,
      searchParams.get(URL_FILTERS[key]) ?? '',
    ]),
  ) as UrlFilters
  const setUrlFilters = (next: Partial<UrlFilters>) => {
    const params = new URLSearchParams(searchParams)
    for (const [key, value] of Object.entries(next) as [UrlFilterKey, string][]) {
      if (value) params.set(URL_FILTERS[key], value)
      else params.delete(URL_FILTERS[key])
    }
    setSearchParams(params, { replace: true })
    setOffset(0)
  }
  // Los filtros finos comparten componente con Gastos e Ingresos; la cuenta
  // ya tiene su selector propio arriba y el contacto no aplica a un traspaso.
  const fine: FineFilterValues = {
    category_id: urlFilters.category_id,
    financial_account_id: '',
    payment_method: urlFilters.payment_method,
    created_by: urlFilters.created_by,
    contact: '',
    min_amount: urlFilters.min_amount,
    max_amount: urlFilters.max_amount,
  }
  const setFine = (next: Partial<FineFilterValues>) => {
    const { financial_account_id: _account, contact: _contact, ...rest } = next
    setUrlFilters(rest)
  }
  const activeFilterCount =
    Number(Boolean(urlFilters.q)) +
    Number(Boolean(urlFilters.start || urlFilters.end)) +
    Number(Boolean(urlFilters.transaction_type)) +
    Number(Boolean(urlFilters.status)) +
    countFineFilters(fine)
  const [filtersOpen, setFiltersOpen] = useState(activeFilterCount > 0)
  const { data: incomeCategories } = useCategories('INCOME')
  const { data: expenseCategories } = useCategories('EXPENSE')
  const categories = useMemo(
    () => [...(incomeCategories ?? []), ...(expenseCategories ?? [])],
    [incomeCategories, expenseCategories],
  )
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ from_account_id: '', to_account_id: '', amount: '', date: today() })

  const { data: accounts } = useAccounts()
  const { hasUnits, hasEntities } = useDimensions()
  // Los mismos parámetros para la lista y la descarga: baja lo que se ve.
  const listParams: Record<string, string> = {
    ...(accountFilter ? { account_id: accountFilter } : {}),
    ...dimensionParams(dimensions),
    ...(urlFilters.q ? { q: urlFilters.q } : {}),
    ...(urlFilters.start ? { start: urlFilters.start } : {}),
    ...(urlFilters.end ? { end: urlFilters.end } : {}),
    ...(urlFilters.transaction_type ? { transaction_type: urlFilters.transaction_type } : {}),
    ...(urlFilters.status ? { status: urlFilters.status } : {}),
    ...fineFilterParams(fine),
  }
  const hasFilters = Object.keys(listParams).length > 0
  const { data, isLoading } = useQuery({
    queryKey: ['transactions', listParams, offset],
    queryFn: async () =>
      (await api.get<Page<Transaction>>('/transactions', { params: { ...listParams, offset } }))
        .data,
  })

  const accountName = useMemo(() => {
    const map = new Map((accounts ?? []).map((account) => [account.id, account.name]))
    return (id: string) => map.get(id) ?? '—'
  }, [accounts])

  const accountNature = useMemo(() => {
    const map = new Map((accounts ?? []).map((account) => [account.id, account.type]))
    return (id: string) => map.get(id)
  }, [accounts])

  const filteredIsCard = accountFilter ? accountNature(accountFilter) === 'CREDIT_CARD' : false

  const transferMutation = useMutation({
    mutationFn: async () => {
      handlePendingApproval(await api.post('/transactions/transfer', form))
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['transactions'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      closeModal()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function closeModal() {
    setTransferOpen(false)
    setError(null)
    setForm({ from_account_id: '', to_account_id: '', amount: '', date: today() })
    if (searchParams.has('transferir')) {
      searchParams.delete('transferir')
      setSearchParams(searchParams, { replace: true })
    }
  }

  const items = data?.items ?? []
  const accountOptions = (accounts ?? [])
    .filter((account) => account.active)
    .map((account) => ({ value: account.id, label: account.name }))

  return (
    <div>
      <PageHeader
        title="Movimientos"
        description="Cada entrada y salida de dinero, cuenta por cuenta."
        actions={
          <>
            <DownloadExcelButton
              path="/transactions/export"
              params={listParams}
              fallbackName="movimientos.xlsx"
            />
            <Button variant="secondary" onClick={() => setTransferOpen(true)}>
              Traspaso entre cuentas
            </Button>
          </>
        }
      >
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-full max-w-xs">
            <SelectInput
              label="Cuenta"
              placeholder="Todas las cuentas"
              options={accountOptions}
              value={accountFilter}
              onChange={(event) => {
                setAccountFilter(event.target.value)
                setOffset(0)
              }}
            />
          </div>
          {hasUnits || hasEntities ? (
            <div className="flex flex-wrap items-center gap-2 pb-0.5">
              <DimensionFilterSelects value={dimensions} onChange={setDimensions} />
            </div>
          ) : null}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <FilterToggle
            count={activeFilterCount}
            open={filtersOpen}
            onToggle={() => setFiltersOpen(!filtersOpen)}
          />
          <DimensionChips value={dimensions} onChange={setDimensions} />
          {urlFilters.q ? (
            <FilterChip label={`"${urlFilters.q}"`} onRemove={() => setUrlFilters({ q: '' })} />
          ) : null}
          {urlFilters.start || urlFilters.end ? (
            <FilterChip
              label={`${urlFilters.start || '…'} → ${urlFilters.end || '…'}`}
              onRemove={() => setUrlFilters({ start: '', end: '' })}
            />
          ) : null}
          {urlFilters.transaction_type ? (
            <FilterChip
              label={TYPE_LABELS[urlFilters.transaction_type]?.label ?? urlFilters.transaction_type}
              onRemove={() => setUrlFilters({ transaction_type: '' })}
            />
          ) : null}
          {urlFilters.status ? (
            <FilterChip
              label={urlFilters.status === 'CANCELLED' ? 'Sólo cancelados' : 'Sólo aplicados'}
              onRemove={() => setUrlFilters({ status: '' })}
            />
          ) : null}
          <FineFilterChips value={fine} onChange={setFine} categories={categories} />
        </div>
        {filtersOpen ? (
          <div className="mt-2 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2.5">
            <input
              type="search"
              placeholder="Buscar por concepto o referencia…"
              value={urlFilters.q}
              onChange={(event) => setUrlFilters({ q: event.target.value })}
              className="w-full rounded-lg border border-border bg-surface px-3 py-1.5 text-sm sm:w-56"
            />
            <div className="flex items-center gap-1.5 text-xs text-muted">
              <span>Del</span>
              <input
                type="date"
                value={urlFilters.start}
                onChange={(event) => setUrlFilters({ start: event.target.value })}
                className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
              />
              <span>al</span>
              <input
                type="date"
                value={urlFilters.end}
                onChange={(event) => setUrlFilters({ end: event.target.value })}
                className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
              />
            </div>
            <select
              aria-label="Tipo"
              value={urlFilters.transaction_type}
              onChange={(event) => setUrlFilters({ transaction_type: event.target.value })}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
            >
              <option value="">Todos los tipos</option>
              {Object.entries(TYPE_LABELS).map(([value, type]) => (
                <option key={value} value={value}>
                  {type.label}
                </option>
              ))}
            </select>
            <select
              aria-label="Estado"
              value={urlFilters.status}
              onChange={(event) => setUrlFilters({ status: event.target.value })}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm"
            >
              <option value="">Aplicados y cancelados</option>
              <option value="ACTIVE">Sólo aplicados</option>
              <option value="CANCELLED">Sólo cancelados</option>
            </select>
            <FineFilterSelects
              value={fine}
              onChange={setFine}
              categories={categories}
              accounts={false}
            />
          </div>
        ) : null}
      </PageHeader>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        hasFilters ? (
          <EmptyState
            title="Nada coincide con lo que buscas"
            message="Prueba con otra cuenta, otro tipo o amplía el rango de fechas."
            action={
              <Button
                variant="secondary"
                onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
              >
                Limpiar filtros
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="Sin movimientos todavía"
            message="Cuando registres ingresos, gastos o traspasos, aquí verás cada peso entrar y salir."
          />
        )
      ) : (
        <Table
          headers={[
            'Fecha',
            'Concepto',
            // Repetir el nombre de la cuenta en cada fila cuando ya filtraste por
            // ella no informa: la columna sólo aparece en la vista de todas.
            ...(accountFilter ? [] : ['Cuenta']),
            ...(hasUnits ? ['Unidad'] : []),
            'Tipo',
            <span key="m" className="block text-right">
              Monto
            </span>,
            ...(accountFilter
              ? [
                  <span key="s" className="block text-right">
                    {filteredIsCard ? 'Debes' : 'Saldo'}
                  </span>,
                ]
              : []),
          ]}
          footer={<TableFooter page={data!} onOffsetChange={setOffset} noun="movimientos" />}
        >
          {items.map((transaction) => {
            const type = TYPE_LABELS[transaction.transaction_type] ?? {
              label: transaction.transaction_type,
              inflow: false,
            }
            const isCard = accountNature(transaction.financial_account_id) === 'CREDIT_CARD'
            return (
              <tr key={transaction.id} className="hover:bg-surface-2/50">
                <td className="whitespace-nowrap px-4 py-2.5 text-muted">{formatDate(transaction.date)}</td>
                <td className="px-4 py-2.5 font-medium">{transaction.description}</td>
                {accountFilter ? null : (
                  <td className="px-4 py-2.5 text-muted">
                    {accountName(transaction.financial_account_id)}
                  </td>
                )}
                {hasUnits ? (
                  <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                    {transaction.business_unit_name ?? '—'}
                  </td>
                ) : null}
                <td className="px-4 py-2.5 text-muted">
                  {isCard ? (type.inflow ? 'Pago de tarjeta' : 'Cargo a tarjeta') : type.label}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <span className="figures font-medium">
                    {/* El signo ya dice la dirección; el color sería redundante.
                        En una tarjeta el dinero no sale: sube lo que debes, así que
                        el signo sigue a la deuda y no al efectivo. */}
                    <Money
                      value={
                        (isCard ? !type.inflow : type.inflow)
                          ? transaction.amount
                          : `-${transaction.amount}`
                      }
                    />
                  </span>
                </td>
                {accountFilter ? (
                  <td className="figures whitespace-nowrap px-4 py-2.5 text-right text-muted">
                    {transaction.running_balance !== null
                      ? formatMoney(transaction.running_balance)
                      : '—'}
                  </td>
                ) : null}
              </tr>
            )
          })}
        </Table>
      )}

      <Modal title="Traspaso entre cuentas" open={transferOpen} onClose={closeModal}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            transferMutation.mutate()
          }}
          className="space-y-4"
        >
          <SelectInput
            label="De la cuenta"
            required
            placeholder="Elige la cuenta de origen"
            options={accountOptions}
            value={form.from_account_id}
            onChange={(event) => setForm({ ...form, from_account_id: event.target.value })}
          />
          <SelectInput
            label="A la cuenta"
            required
            placeholder="Elige la cuenta destino"
            options={accountOptions.filter((option) => option.value !== form.from_account_id)}
            value={form.to_account_id}
            onChange={(event) => setForm({ ...form, to_account_id: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Monto"
              type="number"
              min="0.01"
              step="0.01"
              required
              value={form.amount}
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
            />
            <TextInput
              label="Fecha"
              type="date"
              required
              value={form.date}
              onChange={(event) => setForm({ ...form, date: event.target.value })}
            />
          </div>
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={closeModal}>
              Cancelar
            </Button>
            <Button type="submit" disabled={transferMutation.isPending}>
              Traspasar
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
