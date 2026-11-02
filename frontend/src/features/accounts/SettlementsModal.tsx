import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { useActiveRole } from '@/lib/companies'
import { formatDate, formatMoney, today } from '@/lib/format'
import type { FinancialAccount, Page, Settlement } from '@/types/api'

const ADMIN_ROLES = ['OWNER', 'ADMIN']

/** Registrar una liquidación del procesador (NetPay → banco) y ver su historial.
 *  El bruto sale del procesador, el neto llega al banco y la comisión es gasto. */
export function SettlementsModal({
  processor,
  banks,
  onClose,
}: {
  processor: FinancialAccount | null
  banks: FinancialAccount[]
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const role = useActiveRole()
  const canSettle = role !== null && ADMIN_ROLES.includes(role)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(() => emptyForm(processor))

  const { data: history } = useQuery({
    queryKey: ['settlements', processor?.id],
    queryFn: async () => (await api.get<Page<Settlement>>(`/accounts/${processor!.id}/settlements?limit=20`)).data,
    enabled: processor !== null,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['settlements', processor?.id] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['transactions'] })
    void queryClient.invalidateQueries({ queryKey: ['expenses'] })
  }

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        date: form.date,
        gross_amount: form.gross_amount,
        fee_amount: form.fee_amount || '0',
      }
      if (form.bank_account_id) payload.bank_account_id = form.bank_account_id
      if (form.reference) payload.reference = form.reference
      await api.post(`/accounts/${processor!.id}/settlements`, payload)
    },
    onSuccess: () => {
      invalidate()
      setForm(emptyForm(processor))
      setError(null)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const cancelMutation = useMutation({
    mutationFn: async (settlementId: string) => {
      await api.delete(`/accounts/${processor!.id}/settlements/${settlementId}`)
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const gross = Number(form.gross_amount) || 0
  const fee = Number(form.fee_amount) || 0
  const net = gross - fee
  const pending = Number(processor?.current_balance ?? 0)

  return (
    <Modal title={`Liquidaciones · ${processor?.name ?? ''}`} open={processor !== null} onClose={onClose} size="lg">
      <div className="space-y-6">
        {canSettle ? (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              createMutation.mutate()
            }}
            className="space-y-4"
          >
            <p className="text-sm text-muted">
              Por liquidar: <span className="figures font-medium text-ink">{formatMoney(pending)}</span>. El bruto
              sale del procesador, el neto llega al banco y la comisión se registra como gasto.
            </p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <TextInput
                label="Bruto liquidado"
                type="number"
                min="0.01"
                step="0.01"
                required
                autoFocus
                value={form.gross_amount}
                onChange={(event) => {
                  const grossValue = event.target.value
                  // La comisión se precarga con la tasa pactada; se puede corregir.
                  const rate = Number(processor?.fee_rate ?? 0)
                  const suggested = rate > 0 && grossValue ? (Number(grossValue) * rate).toFixed(2) : form.fee_amount
                  setForm({ ...form, gross_amount: grossValue, fee_amount: suggested })
                }}
              />
              <TextInput
                label="Comisión"
                type="number"
                min="0"
                step="0.01"
                value={form.fee_amount}
                onChange={(event) => setForm({ ...form, fee_amount: event.target.value })}
              />
              <div className="space-y-1">
                <div className="text-[11px] font-semibold tracking-wide text-muted">Neto al banco</div>
                <div className={`figures py-2.5 text-lg font-semibold ${net > 0 ? 'text-ink' : 'text-neg'}`}>
                  {formatMoney(net)}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <TextInput
                label="Fecha del depósito"
                type="date"
                required
                value={form.date}
                onChange={(event) => setForm({ ...form, date: event.target.value })}
              />
              <TextInput
                label="Referencia (opcional)"
                placeholder="Folio del depósito"
                value={form.reference}
                onChange={(event) => setForm({ ...form, reference: event.target.value })}
              />
            </div>
            <SelectInput
              label="Banco donde liquida"
              required
              placeholder="Elige el banco"
              options={banks.map((bank) => ({ value: bank.id, label: bank.name }))}
              value={form.bank_account_id}
              onChange={(event) => setForm({ ...form, bank_account_id: event.target.value })}
            />
            {error ? <p className="text-sm text-neg">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <Button type="submit" disabled={createMutation.isPending || net <= 0}>
                {createMutation.isPending ? 'Registrando…' : 'Registrar liquidación'}
              </Button>
            </div>
          </form>
        ) : (
          <p className="text-sm text-muted">Sólo quien administra la empresa registra liquidaciones.</p>
        )}

        <div>
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Historial</h3>
          {(history?.items ?? []).length === 0 ? (
            <p className="text-sm text-muted">Todavía no hay liquidaciones de este procesador.</p>
          ) : (
            <ul className="divide-y divide-border rounded-lg border border-border">
              {history!.items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <div className="min-w-0">
                    <div className={item.status === 'CANCELLED' ? 'text-muted line-through' : ''}>
                      {formatDate(item.date)}
                      {item.reference ? ` · ${item.reference}` : ''}
                    </div>
                    <div className="text-xs text-muted">
                      Bruto <span className="figures">{formatMoney(item.gross_amount)}</span> · comisión{' '}
                      <span className="figures">{formatMoney(item.fee_amount)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`figures font-medium ${item.status === 'CANCELLED' ? 'text-muted' : 'text-ink'}`}>
                      {formatMoney(item.net_amount)}
                    </span>
                    {item.status === 'ACTIVE' && canSettle ? (
                      <Button
                        variant="ghost"
                        className="!px-2 !py-1 text-xs"
                        disabled={cancelMutation.isPending}
                        onClick={() => {
                          if (window.confirm('¿Cancelar esta liquidación? Se revierten el traspaso y la comisión.')) {
                            cancelMutation.mutate(item.id)
                          }
                        }}
                      >
                        Cancelar
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  )
}

function emptyForm(processor: FinancialAccount | null) {
  return {
    date: today(),
    gross_amount: '',
    fee_amount: '',
    reference: '',
    bank_account_id: processor?.settlement_account_id ?? '',
  }
}
