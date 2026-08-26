import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card } from '@/components/ui/Table'
import { formatMoney } from '@/lib/format'
import { useAccounts } from '@/lib/hooks'

const TYPE_LABELS: Record<string, string> = {
  CASH: 'Efectivo',
  BANK: 'Banco',
  CREDIT_CARD: 'Tarjeta de crédito',
  OTHER: 'Otra',
}

export function AccountsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(searchParams.has('nueva'))
  const [form, setForm] = useState({
    name: '',
    type: 'BANK',
    opening_balance: '',
    institution: '',
    credit_limit: '',
  })
  const [error, setError] = useState<string | null>(null)
  const { data: accounts, isLoading } = useAccounts()

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = { name: form.name, type: form.type }
      if (form.opening_balance) payload.opening_balance = form.opening_balance
      if (form.institution) payload.institution = form.institution
      if (form.type === 'CREDIT_CARD' && form.credit_limit) payload.credit_limit = form.credit_limit
      await api.post('/accounts', payload)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      closeModal()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function closeModal() {
    setModalOpen(false)
    setForm({ name: '', type: 'BANK', opening_balance: '', institution: '', credit_limit: '' })
    setError(null)
    if (searchParams.has('nueva')) {
      searchParams.delete('nueva')
      setSearchParams(searchParams, { replace: true })
    }
  }

  const activos = (accounts ?? []).filter((account) => account.active && !account.is_liability)
  const pasivos = (accounts ?? []).filter((account) => account.active && account.is_liability)
  // Nunca sumar una tarjeta al disponible: su saldo es deuda, no dinero.
  const total = activos.reduce((sum, account) => sum + Number(account.current_balance), 0)
  const deuda = pasivos.reduce((sum, account) => sum + Number(account.current_balance), 0)

  return (
    <div>
      <PageHeader
        title="Cuentas de dinero"
        description="Dónde vive tu dinero: caja, bancos y tarjetas."
        actions={<Button onClick={() => setModalOpen(true)}>+ Nueva cuenta</Button>}
      />

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : (accounts ?? []).length === 0 ? (
        <EmptyState
          title="Sin cuentas todavía"
          message="Agrega tu caja o tu cuenta de banco para empezar a registrar movimientos."
          action={<Button onClick={() => setModalOpen(true)}>Agregar cuenta</Button>}
        />
      ) : (
        <>
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <Card className="flex items-center justify-between">
              <span className="text-sm text-muted">Disponible</span>
              <Money value={total} size="lg" />
            </Card>
            {pasivos.length > 0 ? (
              <Card className="flex items-center justify-between">
                <span className="text-sm text-muted">Deuda en tarjetas</span>
                <Money value={deuda} size="lg" tone={deuda > 0 ? 'neg' : 'ink'} />
              </Card>
            ) : null}
          </div>

          {[
            { title: 'Dónde está tu dinero', items: activos, liability: false },
            { title: 'Lo que debes', items: pasivos, liability: true },
          ]
            .filter((group) => group.items.length > 0)
            .map((group) => (
              <div key={group.title} className="mb-6">
                <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">
                  {group.title}
                </h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  {group.items.map((account) => {
                    // Un activo en negativo es sobregiro: se dice, no se esconde.
                    const overdrawn = !group.liability && Number(account.current_balance) < 0
                    return (
                    <Card
                      key={account.id}
                      className={overdrawn ? '!border-neg/50' : ''}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="truncate font-medium">{account.name}</span>
                            {overdrawn ? (
                              <span className="rounded-full bg-neg/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-neg">
                                Sobregirada
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-0.5 text-xs text-muted">
                            {TYPE_LABELS[account.type] ?? account.type}
                            {account.institution ? ` · ${account.institution}` : ''}
                            {account.last_four ? ` ····${account.last_four}` : ''}
                          </div>
                          {account.available_credit !== null ? (
                            <div className="mt-1.5 text-xs text-muted">
                              Disponible del límite{' '}
                              <span className="figures text-ink">
                                {formatMoney(account.available_credit)}
                              </span>
                            </div>
                          ) : null}
                        </div>
                        <div className="text-right">
                          <Money
                            value={account.current_balance}
                            size="lg"
                            tone={
                              overdrawn || (group.liability && Number(account.current_balance) > 0)
                                ? 'neg'
                                : 'ink'
                            }
                          />
                          {group.liability ? (
                            <div className="text-[10px] uppercase tracking-wide text-muted">debes</div>
                          ) : null}
                        </div>
                      </div>
                    </Card>
                    )
                  })}
                </div>
              </div>
            ))}
        </>
      )}

      <Modal title="Nueva cuenta de dinero" open={modalOpen} onClose={closeModal}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            createMutation.mutate()
          }}
          className="space-y-4"
        >
          <TextInput
            label="Nombre"
            required
            autoFocus
            placeholder="BBVA Operativa"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-4">
            <SelectInput
              label="Tipo"
              required
              options={Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label }))}
              value={form.type}
              onChange={(event) => setForm({ ...form, type: event.target.value })}
            />
            <TextInput
              label={form.type === 'CREDIT_CARD' ? 'Deuda actual' : 'Saldo actual'}
              type="number"
              min="0"
              step="0.01"
              placeholder="0.00"
              hint={
                form.type === 'CREDIT_CARD'
                  ? 'Lo que ya debes en esta tarjeta hoy.'
                  : 'Con cuánto arranca esta cuenta en ARCA.'
              }
              value={form.opening_balance}
              onChange={(event) => setForm({ ...form, opening_balance: event.target.value })}
            />
          </div>
          <TextInput
            label="Institución (opcional)"
            placeholder="BBVA, Santander… (opcional)"
            value={form.institution}
            onChange={(event) => setForm({ ...form, institution: event.target.value })}
          />
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={closeModal}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              Guardar
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
