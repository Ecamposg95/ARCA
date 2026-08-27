/** Recurrentes: lo que se paga igual cada mes, ARCA lo propone solo.
 *
 *  La regla no registra nada. Genera borradores en la Bandeja y la aprobación
 *  humana sigue siendo la única puerta a la contabilidad.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table } from '@/components/ui/Table'
import { TaxSelect } from '@/components/ui/TaxSelect'
import { formatMoney } from '@/lib/format'
import { useAccounts, useCategories, useContacts } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'

interface RecurringRule {
  id: string
  kind: 'INCOME' | 'EXPENSE'
  description: string
  amount: string
  tax_rate: string
  category_id: string
  customer_id: string | null
  vendor_id: string | null
  financial_account_id: string | null
  day_of_month: number
  status: 'ACTIVE' | 'PAUSED'
}

export function currentPeriod(): { year: number; month: number; label: string } {
  const now = new Date()
  const label = now.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' })
  return {
    year: now.getFullYear(),
    month: now.getMonth() + 1,
    label: label.charAt(0).toUpperCase() + label.slice(1),
  }
}

export function usePendingRecurring() {
  const period = currentPeriod()
  return useQuery({
    queryKey: ['recurring', 'pending', period.year, period.month],
    queryFn: async () =>
      (
        await api.get<{ pending: number }>('/recurring/pending', {
          params: { year: period.year, month: period.month },
        })
      ).data.pending,
  })
}

export function RecurringPanel() {
  const queryClient = useQueryClient()
  const defaultTaxRate = useAuthStore((state) => state.organization?.default_tax_rate ?? '0.16')
  const period = currentPeriod()

  const [modalOpen, setModalOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [form, setForm] = useState({
    kind: 'EXPENSE' as 'INCOME' | 'EXPENSE',
    description: '',
    amount: '',
    tax_rate: defaultTaxRate,
    category_id: '',
    contact_id: '',
    financial_account_id: '',
    day_of_month: '1',
  })

  const { data: accounts } = useAccounts()
  const { data: incomeCategories } = useCategories('INCOME')
  const { data: expenseCategories } = useCategories('EXPENSE')
  const { data: customers } = useContacts('customers')
  const { data: vendors } = useContacts('vendors')
  const categories = form.kind === 'INCOME' ? incomeCategories : expenseCategories
  const contacts = form.kind === 'INCOME' ? customers : vendors

  const { data, isLoading } = useQuery({
    queryKey: ['recurring'],
    queryFn: async () =>
      (await api.get<{ items: RecurringRule[] }>('/recurring')).data.items,
  })
  const pendingQuery = usePendingRecurring()

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['recurring'] })
    void queryClient.invalidateQueries({ queryKey: ['proposals'] })
    void queryClient.invalidateQueries({ queryKey: ['proposals-count'] })
  }

  const createRule = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        kind: form.kind,
        description: form.description,
        amount: form.amount,
        tax_rate: form.tax_rate,
        category_id: form.category_id,
        day_of_month: Number(form.day_of_month),
      }
      if (form.financial_account_id) payload.financial_account_id = form.financial_account_id
      if (form.contact_id)
        payload[form.kind === 'INCOME' ? 'customer_id' : 'vendor_id'] = form.contact_id
      await api.post('/recurring', payload)
    },
    onSuccess: () => {
      invalidate()
      setModalOpen(false)
      setError(null)
      setForm({ ...form, description: '', amount: '', contact_id: '' })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggleRule = useMutation({
    mutationFn: async (rule: RecurringRule) => {
      await api.patch(`/recurring/${rule.id}`, {
        status: rule.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE',
      })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const generate = useMutation({
    mutationFn: async () => {
      const response = await api.post('/recurring/generate', {
        year: period.year,
        month: period.month,
      })
      return response.data as { generated: number }
    },
    onSuccess: (result) => {
      invalidate()
      setNotice(
        result.generated === 0
          ? `Nada que generar: los borradores de ${period.label} ya existen.`
          : `${result.generated} borrador(es) de ${period.label} cayeron a la Bandeja para tu aprobación.`,
      )
    },
    onError: (err) => setNotice(errorMessage(err)),
  })

  const rules = data ?? []
  const pending = pendingQuery.data ?? 0

  return (
    <div>
      <PageHeader
        title="Propuestas"
        description="Lo que se repite cada mes: ARCA lo propone solo y tú apruebas."
        actions={
          <div className="flex gap-2">
            {rules.length > 0 ? (
              <Button
                variant="secondary"
                disabled={generate.isPending || pending === 0}
                onClick={() => generate.mutate()}
              >
                {pending > 0
                  ? `Generar borradores de ${period.label} (${pending})`
                  : `${period.label} ya generado`}
              </Button>
            ) : null}
            <Button onClick={() => setModalOpen(true)}>+ Nueva regla</Button>
          </div>
        }
      />

      {notice ? (
        <div className="mb-4 rounded-lg border border-border bg-surface-2 px-4 py-3 text-sm">
          {notice}
          <button
            type="button"
            className="ml-3 text-xs text-muted underline"
            onClick={() => setNotice(null)}
          >
            Cerrar
          </button>
        </div>
      ) : null}

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : rules.length === 0 ? (
        <EmptyState
          title="Nada se repite todavía"
          message="La renta, la nómina, las igualas: registra una vez lo que se paga igual cada mes y ARCA te lo propondrá solo. Tú nada más apruebas."
          action={<Button onClick={() => setModalOpen(true)}>Nueva regla</Button>}
        />
      ) : (
        <Table
          headers={[
            'Se repite',
            'Tipo',
            'Cada mes',
            <span key="m" className="block text-right">
              Monto
            </span>,
            'Estado',
            '',
          ]}
          secondary={[2, 5]}
        >
          {rules.map((rule) => (
            <tr key={rule.id} className="hover:bg-surface-2/50">
              <td className="px-4 py-2.5 font-medium">{rule.description}</td>
              <td className="px-4 py-2.5 text-muted">
                {rule.kind === 'INCOME' ? 'Ingreso' : 'Gasto'}
              </td>
              <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                El día {rule.day_of_month}
              </td>
              <td className="figures px-4 py-2.5 text-right">{formatMoney(rule.amount)}</td>
              <td className="px-4 py-2.5">
                <span
                  className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                    rule.status === 'ACTIVE'
                      ? 'bg-pos/10 text-pos'
                      : 'bg-surface-2 text-muted'
                  }`}
                >
                  {rule.status === 'ACTIVE' ? 'Activa' : 'Pausada'}
                </span>
              </td>
              <td className="px-4 py-2.5 text-right">
                <Button
                  variant="ghost"
                  className="!px-2 !py-1 text-xs"
                  onClick={() => toggleRule.mutate(rule)}
                >
                  {rule.status === 'ACTIVE' ? 'Pausar' : 'Reactivar'}
                </Button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Modal title="Nueva regla recurrente" open={modalOpen} onClose={() => setModalOpen(false)}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            createRule.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <SelectInput
            label="¿Entra o sale dinero?"
            value={form.kind}
            onChange={(event) =>
              setForm({
                ...form,
                kind: event.target.value as 'INCOME' | 'EXPENSE',
                category_id: '',
                contact_id: '',
              })
            }
            options={[
              { value: 'EXPENSE', label: 'Gasto que pago cada mes' },
              { value: 'INCOME', label: 'Ingreso que cobro cada mes' },
            ]}
          />
          <TextInput
            label="¿Qué se repite?"
            placeholder={form.kind === 'EXPENSE' ? 'Renta del coworking' : 'Iguala de soporte'}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
            required
          />
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Monto (con impuesto)"
              type="number"
              step="0.01"
              value={form.amount}
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
              required
            />
            <TaxSelect
              total={form.amount}
              rate={form.tax_rate}
              onRateChange={(rate) => setForm({ ...form, tax_rate: rate })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <SelectInput
              label="Categoría"
              required
              placeholder="Elige una"
              options={(categories ?? []).map((c) => ({ value: c.id, label: c.name }))}
              value={form.category_id}
              onChange={(event) => setForm({ ...form, category_id: event.target.value })}
            />
            <TextInput
              label="¿Qué día del mes? (1–28)"
              type="number"
              min="1"
              max="28"
              value={form.day_of_month}
              onChange={(event) => setForm({ ...form, day_of_month: event.target.value })}
              required
            />
          </div>
          <SelectInput
            label={form.kind === 'INCOME' ? 'Cliente (opcional)' : 'Proveedor (opcional)'}
            placeholder="Sin asignar"
            options={(contacts ?? []).map((c) => ({ value: c.id, label: c.name }))}
            value={form.contact_id}
            onChange={(event) => setForm({ ...form, contact_id: event.target.value })}
          />
          <SelectInput
            label={
              form.kind === 'INCOME'
                ? '¿A qué cuenta entra? (opcional)'
                : '¿Con qué se paga? (opcional)'
            }
            placeholder="Se decide al aprobar"
            options={(accounts ?? []).map((a) => ({ value: a.id, label: a.name }))}
            value={form.financial_account_id}
            onChange={(event) => setForm({ ...form, financial_account_id: event.target.value })}
          />
          <p className="text-xs text-muted">
            Con cuenta, el borrador llega listo como pagado desde ella; sin cuenta, llega por
            pagar y decides después.
          </p>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createRule.isPending}>
              Guardar regla
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
