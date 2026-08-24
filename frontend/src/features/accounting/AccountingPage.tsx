import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { EmptyState } from '@/components/ui/EmptyState'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table } from '@/components/ui/Table'
import { formatDate, formatMoney } from '@/lib/format'
import type { JournalEntry, LedgerAccount, TrialBalanceRow } from '@/types/api'

type Tab = 'diario' | 'balanza' | 'catalogo'

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  ASSET: 'Activo',
  LIABILITY: 'Pasivo',
  EQUITY: 'Capital',
  REVENUE: 'Ingresos',
  EXPENSE: 'Gastos',
}

export function AccountingPage() {
  const [tab, setTab] = useState<Tab>('diario')
  const [expanded, setExpanded] = useState<string | null>(null)

  const accountsQuery = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: async () => (await api.get<LedgerAccount[]>('/accounting/accounts')).data,
  })
  const entriesQuery = useQuery({
    queryKey: ['accounting', 'entries'],
    queryFn: async () =>
      (await api.get<{ items: JournalEntry[]; total: number }>('/accounting/journal-entries')).data,
    enabled: tab === 'diario',
  })
  const trialQuery = useQuery({
    queryKey: ['accounting', 'trial'],
    queryFn: async () =>
      (
        await api.get<{ rows: TrialBalanceRow[]; total_debit: number; total_credit: number }>(
          '/accounting/trial-balance',
        )
      ).data,
    enabled: tab === 'balanza',
  })

  const accountLabel = useMemo(() => {
    const map = new Map((accountsQuery.data ?? []).map((account) => [account.id, `${account.code} ${account.name}`]))
    return (id: string) => map.get(id) ?? id
  }, [accountsQuery.data])

  const tabs: { key: Tab; label: string }[] = [
    { key: 'diario', label: 'Libro diario' },
    { key: 'balanza', label: 'Balanza' },
    { key: 'catalogo', label: 'Catálogo de cuentas' },
  ]

  return (
    <div>
      <PageHeader
        title="Contabilidad"
        description="La partida doble detrás de cada operación. Aquí sí hablamos de cargos y abonos."
      >
        <div className="flex gap-1 rounded-lg border border-border bg-surface p-1 w-fit">
          {tabs.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                tab === item.key ? 'bg-accent text-white font-medium' : 'text-muted hover:text-ink'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </PageHeader>

      {tab === 'diario' ? (
        (entriesQuery.data?.items ?? []).length === 0 ? (
          <EmptyState
            title="Sin pólizas todavía"
            message="Cada ingreso, gasto o traspaso que registres genera aquí su asiento contable automáticamente."
          />
        ) : (
          <div className="space-y-2">
            {(entriesQuery.data?.items ?? []).map((entry) => (
              <div key={entry.id} className="rounded-xl border border-border bg-surface shadow-card">
                <button
                  type="button"
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                  onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}
                >
                  <div>
                    <div className="text-sm font-medium">{entry.description}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {formatDate(entry.date)}
                      {entry.source_type ? ` · origen: ${entry.source_type}` : ''}
                    </div>
                  </div>
                  <span className="figures text-sm text-muted">
                    {formatMoney(entry.lines.reduce((sum, line) => sum + Number(line.debit), 0))}
                  </span>
                </button>
                {expanded === entry.id ? (
                  <div className="border-t border-border px-4 py-2">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs uppercase tracking-wide text-muted">
                          <th className="py-1.5 text-left font-medium">Cuenta</th>
                          <th className="py-1.5 text-right font-medium">Cargo</th>
                          <th className="py-1.5 text-right font-medium">Abono</th>
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
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )
      ) : null}

      {tab === 'balanza' && trialQuery.data ? (
        trialQuery.data.rows.length === 0 ? (
          <EmptyState title="Balanza vacía" message="Registra operaciones y la balanza se armará sola." />
        ) : (
          <Table headers={['Cuenta', <span key="d" className="block text-right">Cargos</span>, <span key="h" className="block text-right">Abonos</span>, <span key="s" className="block text-right">Saldo</span>]}>
            {trialQuery.data.rows.map((row) => (
              <tr key={row.code}>
                <td className="px-4 py-2">
                  <span className="figures mr-2 text-xs text-muted">{row.code}</span>
                  {row.name}
                </td>
                <td className="figures px-4 py-2 text-right">{formatMoney(row.debit)}</td>
                <td className="figures px-4 py-2 text-right">{formatMoney(row.credit)}</td>
                <td className="figures px-4 py-2 text-right font-medium">{formatMoney(row.balance)}</td>
              </tr>
            ))}
            <tr className="bg-surface-2/60 font-semibold">
              <td className="px-4 py-2.5">Totales</td>
              <td className="figures px-4 py-2.5 text-right">{formatMoney(trialQuery.data.total_debit)}</td>
              <td className="figures px-4 py-2.5 text-right">{formatMoney(trialQuery.data.total_credit)}</td>
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
              <td className="px-4 py-2 text-muted">{ACCOUNT_TYPE_LABELS[account.type] ?? account.type}</td>
            </tr>
          ))}
        </Table>
      ) : null}
    </div>
  )
}
