import { Fragment, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api } from '@/api/client'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { TableFooter } from '@/components/ui/Pagination'
import { Segmented } from '@/components/ui/Segmented'
import { Table } from '@/components/ui/Table'
import { formatDate, formatMoney } from '@/lib/format'
import { PERIOD_OPTIONS, rangeForPeriod, type PeriodKey } from '@/lib/periods'
import type { JournalEntry, LedgerAccount, Page, TrialBalanceRow } from '@/types/api'

type Tab = 'diario' | 'balanza' | 'catalogo'

const TABS: { key: Tab; label: string }[] = [
  { key: 'diario', label: 'Libro diario' },
  { key: 'balanza', label: 'Balanza' },
  { key: 'catalogo', label: 'Catálogo de cuentas' },
]

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  ASSET: 'Activo',
  LIABILITY: 'Pasivo',
  EQUITY: 'Capital',
  REVENUE: 'Ingresos',
  EXPENSE: 'Gastos',
}

/** El origen se guarda con el nombre técnico del dominio; aquí se traduce.
 *  Nunca mostrar "payable" o "financial_account" a un usuario. */
const SOURCE_LABELS: Record<string, string> = {
  income: 'Ingreso',
  expense: 'Gasto',
  receivable: 'Cuenta por cobrar',
  payable: 'Cuenta por pagar',
  transfer: 'Traspaso',
  financial_account: 'Saldo inicial',
}

const TYPE_ORDER = ['ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE']

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className={`h-4 w-4 shrink-0 text-muted transition-transform ${open ? 'rotate-90' : ''}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <path d="M6 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function AccountingPage() {
  // La pestaña vive en la URL: se puede compartir y sobrevive a recargar.
  const [searchParams, setSearchParams] = useSearchParams()
  const requested = searchParams.get('vista') as Tab | null
  const tab: Tab = TABS.some((item) => item.key === requested) ? requested! : 'diario'
  const setTab = (next: Tab) => setSearchParams(next === 'diario' ? {} : { vista: next })

  const [expanded, setExpanded] = useState<string | null>(null)
  const [period, setPeriod] = useState<PeriodKey>('current')
  const [offset, setOffset] = useState(0)
  const range = rangeForPeriod(period)

  const accountsQuery = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: async () => (await api.get<LedgerAccount[]>('/accounting/accounts')).data,
  })
  const entriesQuery = useQuery({
    queryKey: ['accounting', 'entries', period, offset],
    queryFn: async () =>
      (await api.get<Page<JournalEntry>>('/accounting/journal-entries', { params: { ...range, offset } })).data,
    enabled: tab === 'diario',
  })
  const trialQuery = useQuery({
    queryKey: ['accounting', 'trial', period],
    queryFn: async () =>
      (
        await api.get<{ rows: TrialBalanceRow[]; total_debit: number; total_credit: number }>(
          '/accounting/trial-balance',
          { params: range.end ? { as_of: range.end } : {} },
        )
      ).data,
    enabled: tab === 'balanza',
  })

  const accountLabel = useMemo(() => {
    const map = new Map(
      (accountsQuery.data ?? []).map((account) => [account.id, `${account.code} ${account.name}`]),
    )
    return (id: string) => map.get(id) ?? id
  }, [accountsQuery.data])

  const trialGroups = useMemo(() => {
    const rows = trialQuery.data?.rows ?? []
    return TYPE_ORDER.map((type) => ({
      type,
      label: ACCOUNT_TYPE_LABELS[type] ?? type,
      rows: rows.filter((row) => row.type === type),
    })).filter((group) => group.rows.length > 0)
  }, [trialQuery.data])

  function changePeriod(next: PeriodKey) {
    setPeriod(next)
    setOffset(0)
    setExpanded(null)
  }

  const balanced =
    trialQuery.data != null && Number(trialQuery.data.total_debit) === Number(trialQuery.data.total_credit)

  return (
    <div>
      <PageHeader
        title="Contabilidad"
        description="La partida doble detrás de cada operación. Aquí sí hablamos de cargos y abonos."
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Segmented options={TABS} value={tab} onChange={setTab} />
          {tab !== 'catalogo' ? (
            <Segmented options={PERIOD_OPTIONS} value={period} onChange={changePeriod} size="sm" />
          ) : null}
        </div>
      </PageHeader>

      {tab === 'diario' ? (
        entriesQuery.isLoading ? (
          <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
        ) : (entriesQuery.data?.items ?? []).length === 0 ? (
          <EmptyState
            title="Sin pólizas en este periodo"
            message="Cada ingreso, gasto, cobro o pago que registres genera aquí su asiento contable automáticamente."
          />
        ) : (
          <Table
            headers={[
              'Folio',
              'Fecha',
              'Concepto',
              'Origen',
              <span key="i" className="block text-right">
                Importe
              </span>,
              '',
            ]}
            footer={
              <TableFooter page={entriesQuery.data!} onOffsetChange={setOffset} noun="pólizas" />
            }
          >
            {(entriesQuery.data?.items ?? []).map((entry) => {
              const total = entry.lines.reduce((sum, line) => sum + Number(line.debit), 0)
              const open = expanded === entry.id
              return (
                <Fragment key={entry.id}>
                  <tr
                    onClick={() => setExpanded(open ? null : entry.id)}
                    className="cursor-pointer hover:bg-surface-2/50"
                  >
                    <td className="figures whitespace-nowrap px-4 py-2.5 text-xs text-muted">
                      {entry.folio}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-muted">{formatDate(entry.date)}</td>
                    <td className="px-4 py-2.5 font-medium">{entry.description}</td>
                    <td className="px-4 py-2.5 text-muted">
                      {entry.source_type ? (SOURCE_LABELS[entry.source_type] ?? entry.source_type) : '—'}
                    </td>
                    <td className="figures whitespace-nowrap px-4 py-2.5 text-right font-medium">
                      {formatMoney(total)}
                    </td>
                    <td className="px-4 py-2.5">
                      <Chevron open={open} />
                    </td>
                  </tr>
                  {open ? (
                    <tr className="bg-surface-2/40">
                      <td colSpan={6} className="px-4 py-3">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-[11px] uppercase tracking-wider text-muted">
                              <th className="pb-1.5 text-left font-semibold">Cuenta</th>
                              <th className="pb-1.5 text-right font-semibold">Cargo</th>
                              <th className="pb-1.5 text-right font-semibold">Abono</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {entry.lines.map((line) => (
                              <tr key={line.id}>
                                <td className="py-1.5">{accountLabel(line.account_id)}</td>
                                <td className="figures py-1.5 text-right">
                                  {Number(line.debit) > 0 ? formatMoney(line.debit) : '—'}
                                </td>
                                <td className="figures py-1.5 text-right">
                                  {Number(line.credit) > 0 ? formatMoney(line.credit) : '—'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </Table>
        )
      ) : null}

      {tab === 'balanza' ? (
        trialQuery.isLoading ? (
          <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
        ) : trialGroups.length === 0 ? (
          <EmptyState title="Balanza vacía" message="Registra operaciones y la balanza se armará sola." />
        ) : (
          <Table
            headers={[
              'Cuenta',
              <span key="c" className="block text-right">
                Cargos
              </span>,
              <span key="a" className="block text-right">
                Abonos
              </span>,
              <span key="s" className="block text-right">
                Saldo
              </span>,
            ]}
          >
            {trialGroups.map((group) => {
              const debit = group.rows.reduce((sum, row) => sum + Number(row.debit), 0)
              const credit = group.rows.reduce((sum, row) => sum + Number(row.credit), 0)
              return (
                <Fragment key={group.type}>
                  <tr className="bg-surface-2/60">
                    <td className="px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
                      {group.label}
                    </td>
                    <td className="figures px-4 py-2 text-right text-xs text-muted">
                      {debit > 0 ? formatMoney(debit) : '—'}
                    </td>
                    <td className="figures px-4 py-2 text-right text-xs text-muted">
                      {credit > 0 ? formatMoney(credit) : '—'}
                    </td>
                    <td />
                  </tr>
                  {group.rows.map((row) => (
                    <tr key={row.code} className="hover:bg-surface-2/40">
                      <td className="px-4 py-2">
                        <span className="figures mr-2 text-xs text-muted">{row.code}</span>
                        {row.name}
                      </td>
                      {/* Columna vacía en vez de $0.00: la vista debe señalar dónde hay dinero. */}
                      <td className="figures px-4 py-2 text-right">
                        {Number(row.debit) > 0 ? formatMoney(row.debit) : <span className="text-muted">—</span>}
                      </td>
                      <td className="figures px-4 py-2 text-right">
                        {Number(row.credit) > 0 ? formatMoney(row.credit) : <span className="text-muted">—</span>}
                      </td>
                      <td className="figures px-4 py-2 text-right font-medium">{formatMoney(row.balance)}</td>
                    </tr>
                  ))}
                </Fragment>
              )
            })}
            <tr className="border-t-2 border-ink/70 font-semibold">
              <td className="px-4 py-2.5">
                Totales
                {balanced ? (
                  <span className="ml-2 text-xs font-medium text-pos">cargos = abonos ✓</span>
                ) : (
                  <span className="ml-2 text-xs font-medium text-neg">no cuadra</span>
                )}
              </td>
              <td className="figures px-4 py-2.5 text-right">
                {formatMoney(trialQuery.data?.total_debit ?? 0)}
              </td>
              <td className="figures px-4 py-2.5 text-right">
                {formatMoney(trialQuery.data?.total_credit ?? 0)}
              </td>
              <td />
            </tr>
          </Table>
        )
      ) : null}

      {tab === 'catalogo' ? (
        <Table headers={['Código', 'Cuenta', 'Tipo']}>
          {(accountsQuery.data ?? []).map((account) => (
            <tr key={account.id} className={account.parent_id ? '' : 'bg-surface-2/40 font-medium'}>
              <td className="figures px-4 py-2">{account.code}</td>
              <td className={`px-4 py-2 ${account.parent_id ? 'pl-8' : ''}`}>{account.name}</td>
              {/* El tipo sólo en la cuenta mayor: repetirlo en cada hija es ruido. */}
              <td className="px-4 py-2 text-muted">
                {account.parent_id ? '' : (ACCOUNT_TYPE_LABELS[account.type] ?? account.type)}
              </td>
            </tr>
          ))}
        </Table>
      ) : null}
    </div>
  )
}
