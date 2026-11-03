/** Detalle de un ingreso o gasto: corregirlo mientras está pendiente y ver su historial.
 *
 *  Pendiente no tiene movimiento ni póliza, así que se puede corregir. Pagado o
 *  cancelado ya no: la corrección es cancelar (reverso) y volver a registrar.
 *  Cada cambio queda en el historial con su valor anterior (HU-09).
 */

import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { HistoryTimeline } from '@/components/ui/HistoryTimeline'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { Segmented } from '@/components/ui/Segmented'
import { StatusBadge } from '@/components/ui/StatusBadge'
import { formatDate } from '@/lib/format'

interface Operation {
  id: string
  date: string
  description: string
  amount: string
  category_id: string
  financial_account_id: string | null
  status: string
  notes: string | null
}

type Tab = 'detail' | 'history'

export function OperationDetailModal({
  operation,
  endpoint,
  paidLabel,
  accountLabel,
  categories,
  accounts,
  categoryName,
  accountName,
  onClose,
  onSaved,
}: {
  operation: Operation | null
  endpoint: string
  paidLabel: string
  accountLabel: string
  categories: { id: string; name: string }[]
  accounts: { id: string; name: string; active: boolean }[]
  categoryName: (id: string) => string
  accountName: (id: string | null) => string
  onClose: () => void
  onSaved: () => void
}) {
  const [tab, setTab] = useState<Tab>('detail')
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    date: '',
    description: '',
    amount: '',
    category_id: '',
    financial_account_id: '',
    notes: '',
  })

  // Abrir otra operación vuelve a la pestaña de detalle; recargar la misma no.
  useEffect(() => {
    setTab('detail')
    setError(null)
  }, [operation?.id])

  useEffect(() => {
    if (!operation) return
    setForm({
      date: operation.date,
      description: operation.description,
      amount: operation.amount,
      category_id: operation.category_id,
      financial_account_id: operation.financial_account_id ?? '',
      notes: operation.notes ?? '',
    })
  }, [operation])

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!operation) return
      // Sólo lo que cambió: el historial registra exactamente lo que se tocó.
      const payload: Record<string, unknown> = {}
      if (form.date !== operation.date) payload.date = form.date
      if (form.description.trim() !== operation.description) payload.description = form.description.trim()
      if (Number(form.amount) !== Number(operation.amount)) payload.amount = form.amount
      if (form.category_id !== operation.category_id) payload.category_id = form.category_id
      if (form.financial_account_id !== (operation.financial_account_id ?? ''))
        payload.financial_account_id = form.financial_account_id || null
      if (form.notes !== (operation.notes ?? '')) payload.notes = form.notes || null
      if (Object.keys(payload).length === 0) return
      await api.patch(`${endpoint}/${operation.id}`, payload)
    },
    onSuccess: () => {
      setError(null)
      onSaved()
      setTab('history')
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (!operation) return null
  const editable = operation.status === 'PENDING'

  return (
    <Modal title={operation.description} open onClose={onClose}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <Segmented<Tab>
          size="sm"
          options={[
            { key: 'detail', label: 'Detalle' },
            { key: 'history', label: 'Historial' },
          ]}
          value={tab}
          onChange={setTab}
        />
        <StatusBadge status={operation.status} paidLabel={paidLabel} />
      </div>

      {tab === 'history' ? (
        <div className="max-h-[60vh] overflow-y-auto pr-1">
          <HistoryTimeline endpoint={endpoint} entityId={operation.id} />
        </div>
      ) : editable ? (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            saveMutation.mutate()
          }}
        >
          <TextInput
            label="Concepto"
            required
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <TextInput
              label="Monto total"
              required
              inputMode="decimal"
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
          <SelectInput
            label="Categoría"
            required
            options={categories.map((category) => ({ value: category.id, label: category.name }))}
            value={form.category_id}
            onChange={(event) => setForm({ ...form, category_id: event.target.value })}
          />
          <SelectInput
            label={`${accountLabel} (opcional)`}
            placeholder="Todavía no lo sé"
            options={accounts
              .filter((account) => account.active || account.id === form.financial_account_id)
              .map((account) => ({ value: account.id, label: account.name }))}
            value={form.financial_account_id}
            onChange={(event) => setForm({ ...form, financial_account_id: event.target.value })}
          />
          <TextInput
            label="Notas (opcional)"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
          <p className="text-xs text-muted">
            Cada cambio queda en el historial con su valor anterior.
          </p>
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cerrar
            </Button>
            <Button type="submit" disabled={saveMutation.isPending}>
              {saveMutation.isPending ? 'Guardando…' : 'Guardar cambios'}
            </Button>
          </div>
        </form>
      ) : (
        <div className="space-y-3 text-sm">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
            <dt className="text-muted">Monto</dt>
            <dd>
              <Money value={operation.amount} tone="ink" />
            </dd>
            <dt className="text-muted">Fecha</dt>
            <dd>{formatDate(operation.date)}</dd>
            <dt className="text-muted">Categoría</dt>
            <dd>{categoryName(operation.category_id)}</dd>
            <dt className="text-muted">Cuenta</dt>
            <dd>{accountName(operation.financial_account_id)}</dd>
            {operation.notes ? (
              <>
                <dt className="text-muted">Notas</dt>
                <dd>{operation.notes}</dd>
              </>
            ) : null}
          </dl>
          <p className="text-xs text-muted">
            {operation.status === 'CANCELLED'
              ? 'Está cancelada: ya no se puede modificar.'
              : 'Ya movió dinero: para corregirla, cancélala y regístrala de nuevo. Así la contabilidad conserva el rastro.'}
          </p>
        </div>
      )}
    </Modal>
  )
}
