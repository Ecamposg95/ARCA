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
import { Table } from '@/components/ui/Table'
import { TableFooter } from '@/components/ui/Pagination'
import { formatDate, formatMoney, today } from '@/lib/format'
import { useAccounts } from '@/lib/hooks'
import type { Page, Transaction } from '@/types/api'

const TYPE_LABELS: Record<string, { label: string; inflow: boolean }> = {
  INCOME: { label: 'Ingreso', inflow: true },
  EXPENSE: { label: 'Gasto', inflow: false },
  TRANSFER_IN: { label: 'Traspaso (entrada)', inflow: true },
  TRANSFER_OUT: { label: 'Traspaso (salida)', inflow: false },
  RECEIVABLE_COLLECTION: { label: 'Cobro', inflow: true },
  PAYABLE_PAYMENT: { label: 'Pago', inflow: false },
  ADJUSTMENT: { label: 'Ajuste', inflow: false },
}

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
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({ from_account_id: '', to_account_id: '', amount: '', date: today() })

  const { data: accounts } = useAccounts()
  const { data, isLoading } = useQuery({
    queryKey: ['transactions', accountFilter, offset],
    queryFn: async () =>
      (
        await api.get<Page<Transaction>>('/transactions', {
          params: { ...(accountFilter ? { account_id: accountFilter } : {}), offset },
        })
      ).data,
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
      await api.post('/transactions/transfer', form)
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
          <Button variant="secondary" onClick={() => setTransferOpen(true)}>
            Traspaso entre cuentas
          </Button>
        }
      >
        <div className="max-w-xs">
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
      </PageHeader>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        <EmptyState
          title="Sin movimientos todavía"
          message="Cuando registres ingresos, gastos o traspasos, aquí verás cada peso entrar y salir."
        />
      ) : (
        <Table
          headers={[
            'Fecha',
            'Concepto',
            // Repetir el nombre de la cuenta en cada fila cuando ya filtraste por
            // ella no informa: la columna sólo aparece en la vista de todas.
            ...(accountFilter ? [] : ['Cuenta']),
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
