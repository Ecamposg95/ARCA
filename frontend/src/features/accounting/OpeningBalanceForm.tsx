/** Saldos iniciales: la empresa llega a ARCA con lo que traía en CONTPAQi.
 *
 *  Una rejilla con las cuentas de balance que admiten captura; cada saldo va en
 *  la naturaleza de su cuenta y la diferencia la absorbe la cuenta de cuadre
 *  (3200 o 3100). Las cuentas con saldo espejo se muestran en gris: abren desde
 *  su módulo. El backend vuelve a validar todo. */

import { Fragment, useMemo, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { formatMoney, today } from '@/lib/format'
import type { JournalEntry, LedgerAccount } from '@/types/api'

/** Importe en captura: hasta 12 enteros y dos decimales (mismo patrón que JournalEntryForm). */
const AMOUNT_PATTERN = /^\d{0,12}(\.\d{0,2})?$/

const BALANCE_TYPES = ['ASSET', 'LIABILITY', 'EQUITY']

const BALANCING_OPTIONS = [
  { value: '3200', label: '3200 · Resultados Acumulados' },
  { value: '3100', label: '3100 · Capital' },
]

/** Dónde se captura el saldo de cada cuenta con saldo espejo (rules.MODULE_CONTROLLED_CODES). */
const MODULE_OF: Record<string, string> = {
  '1100': 'Movimientos',
  '2200': 'Movimientos',
  '1200': 'Por cobrar y Por pagar',
  '2100': 'Por cobrar y Por pagar',
  '1400': 'Patrimonio',
  '1490': 'Patrimonio',
  '2300': 'Patrimonio',
}

function toNumber(value: string | undefined): number {
  const parsed = Number(value ?? '')
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

/** Centavos enteros: los totales se acumulan sin aritmética de punto flotante sobre dinero. */
const toCents = (value: string | undefined) => Math.round(toNumber(value) * 100)

const lastYearEnd = () => `${new Date().getFullYear() - 1}-12-31`

const cellInput =
  'w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-ink placeholder:text-muted/50 hover:border-muted/40'

export function OpeningBalanceForm({
  open,
  onClose,
  accounts,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  accounts: LedgerAccount[]
  onSaved: (entry: JournalEntry) => void
}) {
  const queryClient = useQueryClient()
  const [date, setDate] = useState(lastYearEnd())
  const [balancingCode, setBalancingCode] = useState('3200')
  const [amounts, setAmounts] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const balancing = accounts.find((account) => account.code === balancingCode)

  // Cuentas de detalle, activas y de balance, agrupadas bajo su mayor.
  const { groups, controlled } = useMemo(() => {
    const detail = accounts
      .filter((a) => a.parent_id && a.active && BALANCE_TYPES.includes(a.type))
      .sort((a, b) => a.code.localeCompare(b.code))
    const majors = accounts
      .filter((a) => !a.parent_id && BALANCE_TYPES.includes(a.type))
      .sort((a, b) => a.code.localeCompare(b.code))
    return {
      groups: majors
        .map((major) => ({
          major,
          rows: detail.filter((a) => a.parent_id === major.id && a.manual_allowed && a.code !== balancingCode),
        }))
        .filter((group) => group.rows.length > 0),
      controlled: detail.filter((a) => !a.manual_allowed),
    }
  }, [accounts, balancingCode])

  // Lo que se envía: sólo cuentas visibles con saldo. Cambiar la cuenta de cuadre
  // saca su renglón de la rejilla y también su importe.
  const filled = groups
    .flatMap((group) => group.rows)
    .filter((account) => toNumber(amounts[account.id]) > 0)
  const assetsCents = filled.filter((a) => a.type === 'ASSET').reduce((sum, a) => sum + toCents(amounts[a.id]), 0)
  const liabilitiesAndEquityCents = filled
    .filter((a) => a.type !== 'ASSET')
    .reduce((sum, a) => sum + toCents(amounts[a.id]), 0)
  // Activo mayor que pasivo y capital: la diferencia se abona a la cuenta de cuadre (sube el capital).
  const residualCents = assetsCents - liabilitiesAndEquityCents
  const assets = assetsCents / 100
  const liabilitiesAndEquity = liabilitiesAndEquityCents / 100
  const residual = residualCents / 100
  const canSave = filled.length > 0 && Boolean(date)

  function reset() {
    setDate(lastYearEnd())
    setBalancingCode('3200')
    setAmounts({})
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<JournalEntry>('/accounting/opening-balance', {
          date,
          description: null,
          balancing_code: balancingCode,
          lines: filled.map((account) => ({
            account_id: account.id,
            amount: toNumber(amounts[account.id]).toFixed(2),
          })),
        })
      ).data,
    onSuccess: (entry) => {
      void queryClient.invalidateQueries({ queryKey: ['accounting'] })
      void queryClient.invalidateQueries({ queryKey: ['periods'] })
      reset()
      onSaved(entry)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function close() {
    setError(null)
    onClose()
  }

  return (
    <Modal title="Saldos iniciales" open={open} onClose={close} size="lg">
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          if (save.isPending) return
          if (canSave) save.mutate()
        }}
      >
        <p className="text-sm text-muted">
          Captura el saldo de cada cuenta al día de corte, en su naturaleza. La diferencia entre activo y pasivo
          más capital va a la cuenta de cuadre.
        </p>
        <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
          <TextInput
            label="Fecha de corte"
            type="date"
            value={date}
            max={today()}
            onChange={(e) => setDate(e.target.value)}
            required
          />
          <SelectInput
            label="Cuadrar contra"
            value={balancingCode}
            options={BALANCING_OPTIONS}
            onChange={(e) => setBalancingCode(e.target.value)}
          />
        </div>

        <div className="max-h-[50vh] overflow-y-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-2 py-2 font-semibold">Código</th>
                <th className="px-2 py-2 font-semibold">Cuenta</th>
                <th className="px-2 py-2 font-semibold">Naturaleza</th>
                <th className="w-40 px-2 py-2 text-right font-semibold">Saldo</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {groups.map(({ major, rows }) => (
                <Fragment key={major.id}>
                  <tr className="bg-surface-2/60">
                    <td className="figures px-2 py-1.5 text-xs text-muted">{major.code}</td>
                    <td className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted" colSpan={3}>
                      {major.name}
                    </td>
                  </tr>
                  {rows.map((account) => (
                    <tr key={account.id}>
                      <td className="figures px-2 py-1.5 text-muted">{account.code}</td>
                      <td className="px-2 py-1.5">{account.name}</td>
                      <td className="px-2 py-1.5 text-muted">{account.type === 'ASSET' ? 'Deudora' : 'Acreedora'}</td>
                      <td className="px-2 py-1.5">
                        <input
                          aria-label={`Saldo de ${account.code} ${account.name}`}
                          className={`${cellInput} figures text-right`}
                          inputMode="decimal"
                          placeholder="0.00"
                          value={amounts[account.id] ?? ''}
                          onChange={(e) => {
                            if (!AMOUNT_PATTERN.test(e.target.value)) return
                            setAmounts((prev) => ({ ...prev, [account.id]: e.target.value }))
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
              {controlled.map((account) => (
                <tr key={account.id} className="text-muted">
                  <td className="figures px-2 py-1.5">{account.code}</td>
                  <td className="px-2 py-1.5">{account.name}</td>
                  <td className="px-2 py-1.5 text-xs" colSpan={2}>
                    Se captura desde {MODULE_OF[account.code] ?? 'su módulo'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <dl className="grid gap-2 rounded-lg bg-surface-2/60 px-4 py-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted">Activo</dt>
            <dd className="figures font-semibold">{formatMoney(assets)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Pasivo y capital</dt>
            <dd className="figures font-semibold">{formatMoney(liabilitiesAndEquity)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">
              Va a {balancingCode} {balancing?.name ?? ''}
            </dt>
            <dd className={`figures font-semibold ${residual < 0 ? 'text-neg' : ''}`}>
              {residual === 0 ? formatMoney(0) : `${residual > 0 ? '+' : '−'}${formatMoney(Math.abs(residual))}`}
              <span className="ml-1 text-xs font-normal text-muted">
                {residual > 0 ? 'abono' : residual < 0 ? 'cargo' : 'sin diferencia'}
              </span>
            </dd>
          </div>
        </dl>

        <div className="flex items-center justify-end gap-3">
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <Button type="button" variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" disabled={!canSave || save.isPending}>
            {save.isPending ? 'Guardando…' : 'Guardar saldos iniciales'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
