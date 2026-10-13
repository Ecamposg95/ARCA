/** Captura de una póliza de diario: la rejilla que un contador espera, con
 *  totales vivos y sin botón de guardar hasta que cuadre. El backend vuelve a
 *  validar todo; aquí sólo evitamos viajes inútiles. */

import { useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { formatMoney, today } from '@/lib/format'
import type { JournalEntry, LedgerAccount } from '@/types/api'

/** Cuentas con saldo espejo fuera del ledger: se mueven desde su módulo. */
const MODULE_CONTROLLED = new Set(['1100', '1200', '2100', '2200'])

interface Line {
  account_id: string
  debit: string
  credit: string
  description: string
}

const emptyLine = (): Line => ({ account_id: '', debit: '', credit: '', description: '' })

function toNumber(value: string): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

const cents = (value: number) => Math.round(value * 100) / 100

const cellInput =
  'w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-ink placeholder:text-muted/50 hover:border-muted/40'

export function JournalEntryForm({
  open,
  onClose,
  accounts,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  accounts: LedgerAccount[]
  onCreated: (entry: JournalEntry) => void
}) {
  const queryClient = useQueryClient()
  const [date, setDate] = useState(today())
  const [description, setDescription] = useState('')
  const [reference, setReference] = useState('')
  const [lines, setLines] = useState<Line[]>([emptyLine(), emptyLine()])
  const [error, setError] = useState<string | null>(null)

  const options = useMemo(
    () => accounts.filter((a) => a.parent_id && a.active && !MODULE_CONTROLLED.has(a.code)),
    [accounts],
  )

  const totalDebit = cents(lines.reduce((sum, line) => sum + toNumber(line.debit), 0))
  const totalCredit = cents(lines.reduce((sum, line) => sum + toNumber(line.credit), 0))
  const difference = cents(totalDebit - totalCredit)
  const filled = lines.filter((line) => line.account_id && (toNumber(line.debit) > 0 || toNumber(line.credit) > 0))
  const canSave = description.trim().length > 0 && filled.length >= 2 && difference === 0 && totalDebit > 0

  function reset() {
    setDate(today())
    setDescription('')
    setReference('')
    setLines([emptyLine(), emptyLine()])
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<JournalEntry>('/accounting/journal-entries', {
          date,
          description: description.trim(),
          reference: reference.trim() || null,
          lines: filled.map((line) => ({
            account_id: line.account_id,
            debit: toNumber(line.debit).toFixed(2),
            credit: toNumber(line.credit).toFixed(2),
            description: line.description.trim() || null,
          })),
        })
      ).data,
    onSuccess: (entry) => {
      void queryClient.invalidateQueries({ queryKey: ['accounting'] })
      reset()
      onCreated(entry)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function updateLine(index: number, patch: Partial<Line>) {
    setLines((prev) => {
      const next = prev.map((line, i) => (i === index ? { ...line, ...patch } : line))
      // Teclear en la última línea abre otra: capturar diez líneas no debe pedir diez clics.
      if (index === prev.length - 1 && next.length < 100) next.push(emptyLine())
      return next
    })
  }

  function removeLine(index: number) {
    setLines((prev) => (prev.length > 2 ? prev.filter((_, i) => i !== index) : prev))
  }

  function close() {
    reset()
    onClose()
  }

  return (
    <Modal title="Nueva póliza de diario" open={open} onClose={close} size="lg">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (canSave) save.mutate()
        }}
      >
        <div className="grid gap-3 sm:grid-cols-[10rem_1fr_10rem]">
          <TextInput label="Fecha" type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} required />
          <TextInput
            label="Concepto"
            value={description}
            maxLength={500}
            placeholder="Provisión de nómina de la 2a quincena"
            onChange={(e) => setDescription(e.target.value)}
            required
          />
          <TextInput
            label="Referencia (opcional)"
            value={reference}
            maxLength={100}
            placeholder="NOM-10"
            onChange={(e) => setReference(e.target.value)}
          />
        </div>

        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-2 py-2 font-semibold">Cuenta</th>
                <th className="w-32 px-2 py-2 text-right font-semibold">Cargo</th>
                <th className="w-32 px-2 py-2 text-right font-semibold">Abono</th>
                <th className="px-2 py-2 font-semibold">Concepto de la línea</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {lines.map((line, index) => (
                <tr key={index}>
                  <td className="px-2 py-1.5">
                    <select
                      aria-label={`Cuenta de la línea ${index + 1}`}
                      className={cellInput}
                      value={line.account_id}
                      onChange={(e) => updateLine(index, { account_id: e.target.value })}
                    >
                      <option value="">Elige una cuenta</option>
                      {options.map((account) => (
                        <option key={account.id} value={account.id}>
                          {account.code} · {account.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Cargo de la línea ${index + 1}`}
                      className={`${cellInput} figures text-right`}
                      inputMode="decimal"
                      placeholder="0.00"
                      value={line.debit}
                      onChange={(e) => updateLine(index, { debit: e.target.value, credit: e.target.value ? '' : line.credit })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Abono de la línea ${index + 1}`}
                      className={`${cellInput} figures text-right`}
                      inputMode="decimal"
                      placeholder="0.00"
                      value={line.credit}
                      onChange={(e) => updateLine(index, { credit: e.target.value, debit: e.target.value ? '' : line.debit })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      aria-label={`Concepto de la línea ${index + 1}`}
                      className={cellInput}
                      maxLength={500}
                      value={line.description}
                      onChange={(e) => updateLine(index, { description: e.target.value })}
                    />
                  </td>
                  <td className="px-1 py-1.5 text-center">
                    <button
                      type="button"
                      aria-label={`Quitar la línea ${index + 1}`}
                      className="rounded p-1 text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-30"
                      disabled={lines.length <= 2}
                      onClick={() => removeLine(index)}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-ink/70 font-semibold">
                <td className="px-2 py-2">Totales</td>
                <td className="figures px-2 py-2 text-right">{formatMoney(totalDebit)}</td>
                <td className="figures px-2 py-2 text-right">{formatMoney(totalCredit)}</td>
                <td className="px-2 py-2 text-xs" colSpan={2}>
                  {difference === 0 && totalDebit > 0 ? (
                    <span className="text-pos">cargos = abonos ✓</span>
                  ) : (
                    <span className="text-muted">
                      Diferencia <span className="figures text-neg">{formatMoney(Math.abs(difference))}</span>
                    </span>
                  )}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="flex items-center justify-between gap-3">
          <Button type="button" variant="ghost" onClick={() => setLines((prev) => [...prev, emptyLine()])}>
            + Agregar línea
          </Button>
          <div className="flex items-center gap-3">
            {error ? <p className="text-sm text-neg">{error}</p> : null}
            <Button type="button" variant="secondary" onClick={close}>
              Cancelar
            </Button>
            <Button type="submit" disabled={!canSave || save.isPending}>
              {save.isPending ? 'Guardando…' : 'Guardar póliza'}
            </Button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
