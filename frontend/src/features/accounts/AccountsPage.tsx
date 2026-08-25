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
  const [form, setForm] = useState({ name: '', type: 'BANK', opening_balance: '', institution: '' })
  const [error, setError] = useState<string | null>(null)
  const { data: accounts, isLoading } = useAccounts()

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = { name: form.name, type: form.type }
      if (form.opening_balance) payload.opening_balance = form.opening_balance
      if (form.institution) payload.institution = form.institution
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
    setForm({ name: '', type: 'BANK', opening_balance: '', institution: '' })
    setError(null)
    if (searchParams.has('nueva')) {
      searchParams.delete('nueva')
      setSearchParams(searchParams, { replace: true })
    }
  }

  const total = (accounts ?? [])
    .filter((account) => account.active)
    .reduce((sum, account) => sum + Number(account.current_balance), 0)

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
          <Card className="mb-4 flex items-center justify-between">
            <span className="text-sm text-muted">Total disponible</span>
            <Money value={total} size="lg" />
          </Card>
          <div className="grid gap-4 sm:grid-cols-2">
            {(accounts ?? []).map((account) => (
              <Card key={account.id} className={account.active ? '' : 'opacity-60'}>
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium">{account.name}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {TYPE_LABELS[account.type] ?? account.type}
                      {account.institution ? ` · ${account.institution}` : ''}
                      {account.last_four ? ` ····${account.last_four}` : ''}
                    </div>
                  </div>
                  <Money value={account.current_balance} size="lg" />
                </div>
              </Card>
            ))}
          </div>
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
              label="Saldo actual"
              type="number"
              min="0"
              step="0.01"
              placeholder="0.00"
              hint="Con cuánto arranca esta cuenta en ARCA."
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
