/** Patrimonio: lo que compraste para usar años y lo que debes a plazos.
 *
 *  Viven juntos porque responden la misma pregunta —cuánto vale el negocio— y
 *  porque ambos se comportan igual: nacen de una operación y se van moviendo
 *  mes a mes sin que nadie los toque.
 */

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
import { Card, Table } from '@/components/ui/Table'
import { formatDate, formatMoney, today } from '@/lib/format'
import { useAccounts } from '@/lib/hooks'
import type { FixedAsset, Loan, LoanSchedule, Page } from '@/types/api'

const ASSET_CATEGORIES = [
  { value: 'EQUIPO_COMPUTO', label: 'Equipo de cómputo', months: 36 },
  { value: 'MOBILIARIO', label: 'Mobiliario', months: 120 },
  { value: 'VEHICULOS', label: 'Vehículos', months: 48 },
  { value: 'MAQUINARIA', label: 'Maquinaria', months: 120 },
  { value: 'EDIFICIOS', label: 'Edificios', months: 240 },
  { value: 'OTRO', label: 'Otro', months: 60 },
]

function lastClosedMonth(): { year: number; month: number; label: string } {
  const now = new Date()
  const end = new Date(now.getFullYear(), now.getMonth(), 0)
  return {
    year: end.getFullYear(),
    month: end.getMonth() + 1,
    label: end.toLocaleDateString('es-MX', { month: 'long', year: 'numeric' }),
  }
}

export function AssetsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = searchParams.get('vista') === 'prestamos' ? 'prestamos' : 'activos'
  const setTab = (next: string) =>
    setSearchParams(next === 'activos' ? {} : { vista: next }, { replace: true })

  const [assetModal, setAssetModal] = useState(false)
  const [loanModal, setLoanModal] = useState(false)
  const [payTarget, setPayTarget] = useState<Loan | null>(null)
  const [scheduleFor, setScheduleFor] = useState<Loan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const { data: accounts } = useAccounts()
  const closed = useMemo(lastClosedMonth, [])

  const assetsQuery = useQuery({
    queryKey: ['fixed-assets'],
    queryFn: async () => (await api.get<Page<FixedAsset>>('/fixed-assets')).data,
    enabled: tab === 'activos',
  })
  const assetSummary = useQuery({
    queryKey: ['fixed-assets', 'summary'],
    queryFn: async () => (await api.get('/fixed-assets/summary')).data,
    enabled: tab === 'activos',
  })
  const loansQuery = useQuery({
    queryKey: ['loans'],
    queryFn: async () => (await api.get<Page<Loan>>('/loans')).data,
    enabled: tab === 'prestamos',
  })
  const loanSummary = useQuery({
    queryKey: ['loans', 'summary'],
    queryFn: async () => (await api.get('/loans/summary')).data,
    enabled: tab === 'prestamos',
  })
  const scheduleQuery = useQuery({
    queryKey: ['loans', 'schedule', scheduleFor?.id],
    queryFn: async () => (await api.get<LoanSchedule>(`/loans/${scheduleFor!.id}/schedule`)).data,
    enabled: scheduleFor !== null,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['fixed-assets'] })
    void queryClient.invalidateQueries({ queryKey: ['loans'] })
    void queryClient.invalidateQueries({ queryKey: ['accounts'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['reports'] })
  }

  const [assetForm, setAssetForm] = useState({
    name: '',
    category: 'EQUIPO_COMPUTO',
    acquisition_date: today(),
    cost: '',
    tax_amount: '',
    salvage_value: '',
    useful_life_months: '36',
    financial_account_id: '',
  })
  const [loanForm, setLoanForm] = useState({
    lender: '',
    description: '',
    principal: '',
    annual_rate: '0.24',
    term_months: '12',
    start_date: today(),
    financial_account_id: '',
  })
  const [payForm, setPayForm] = useState({ amount: '', financial_account_id: '', date: today() })

  const createAsset = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        name: assetForm.name,
        category: assetForm.category,
        acquisition_date: assetForm.acquisition_date,
        cost: assetForm.cost,
        useful_life_months: Number(assetForm.useful_life_months),
      }
      if (assetForm.tax_amount) payload.tax_amount = assetForm.tax_amount
      if (assetForm.salvage_value) payload.salvage_value = assetForm.salvage_value
      if (assetForm.financial_account_id)
        payload.financial_account_id = assetForm.financial_account_id
      await api.post('/fixed-assets', payload)
    },
    onSuccess: () => {
      invalidate()
      setAssetModal(false)
      setError(null)
      setAssetForm({ ...assetForm, name: '', cost: '', tax_amount: '', salvage_value: '' })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const createLoan = useMutation({
    mutationFn: async () => {
      await api.post('/loans', {
        lender: loanForm.lender,
        description: loanForm.description,
        principal: loanForm.principal,
        annual_rate: loanForm.annual_rate,
        term_months: Number(loanForm.term_months),
        start_date: loanForm.start_date,
        ...(loanForm.financial_account_id
          ? { financial_account_id: loanForm.financial_account_id }
          : {}),
      })
    },
    onSuccess: () => {
      invalidate()
      setLoanModal(false)
      setError(null)
      setLoanForm({ ...loanForm, lender: '', description: '', principal: '' })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const payLoan = useMutation({
    mutationFn: async () => {
      await api.post(`/loans/${payTarget!.id}/pay`, payForm)
    },
    onSuccess: () => {
      invalidate()
      setPayTarget(null)
      setError(null)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const depreciate = useMutation({
    mutationFn: async () => {
      const response = await api.post('/fixed-assets/depreciate', {
        year: closed.year,
        month: closed.month,
      })
      return response.data
    },
    onSuccess: (data: { posted: unknown[]; total: string }) => {
      invalidate()
      setNotice(
        data.posted.length === 0
          ? `No había nada que depreciar en ${closed.label}.`
          : `Se registró la depreciación de ${closed.label}: ${formatMoney(data.total)} en ${data.posted.length} activo(s).`,
      )
    },
    onError: (err) => setNotice(errorMessage(err)),
  })

  const accountOptions = (accounts ?? []).map((account) => ({
    value: account.id,
    label: account.name,
  }))

  const assets = assetsQuery.data?.items ?? []
  const loans = loansQuery.data?.items ?? []

  return (
    <div>
      <PageHeader
        title="Patrimonio"
        description="Lo que compraste para usar años y lo que debes a plazos."
        actions={
          tab === 'activos' ? (
            <Button onClick={() => setAssetModal(true)}>+ Nuevo activo</Button>
          ) : (
            <Button onClick={() => setLoanModal(true)}>+ Nuevo préstamo</Button>
          )
        }
      >
        <div className="flex gap-2">
          {[
            { key: 'activos', label: 'Activos fijos' },
            { key: 'prestamos', label: 'Préstamos' },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setTab(item.key)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                tab === item.key
                  ? 'bg-accent text-on-accent'
                  : 'border border-border bg-surface text-muted hover:text-ink'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </PageHeader>

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

      {tab === 'activos' ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Valor en libros</p>
              <Money value={assetSummary.data?.book_value ?? 0} size="lg" />
              <p className="mt-1 text-xs text-muted">
                Costo {formatMoney(assetSummary.data?.total_cost ?? 0)} − depreciado{' '}
                {formatMoney(assetSummary.data?.accumulated_depreciation ?? 0)}
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Depreciación mensual</p>
              <Money value={assetSummary.data?.monthly_depreciation ?? 0} size="lg" />
              <p className="mt-1 text-xs text-muted">Lo que este equipo te cuesta cada mes</p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Cierre pendiente</p>
              <p className="mt-1 text-sm">
                Registrar la depreciación de <span className="font-medium">{closed.label}</span>
              </p>
              <Button
                variant="secondary"
                className="mt-2 !px-3 !py-1 text-xs"
                disabled={depreciate.isPending}
                onClick={() => depreciate.mutate()}
              >
                {depreciate.isPending ? 'Registrando…' : 'Registrar depreciación'}
              </Button>
            </Card>
          </div>

          {assets.length === 0 ? (
            <EmptyState
              title="Sin activos registrados"
              message="Una laptop, un vehículo o el mobiliario no son gasto del mes: se usan durante años. Regístralos aquí y ARCA los deprecia solo."
              action={<Button onClick={() => setAssetModal(true)}>Nuevo activo</Button>}
            />
          ) : (
            <Table
              headers={[
                'Activo',
                'Comprado',
                <span key="c" className="block text-right">
                  Costo
                </span>,
                <span key="d" className="block text-right">
                  Depreciado
                </span>,
                <span key="v" className="block text-right">
                  Vale hoy
                </span>,
                'Le quedan',
              ]}
              secondary={[2, 4]}
            >
              {assets.map((asset) => (
                <tr key={asset.id} className="hover:bg-surface-2/50">
                  <td className="px-4 py-2.5">
                    <div className="font-medium">{asset.name}</div>
                    <div className="text-xs text-muted">
                      {ASSET_CATEGORIES.find((c) => c.value === asset.category)?.label ??
                        asset.category}
                      {asset.status === 'DISPOSED' ? ' · dado de baja' : ''}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                    {formatDate(asset.acquisition_date)}
                  </td>
                  <td className="figures px-4 py-2.5 text-right">{formatMoney(asset.cost)}</td>
                  <td className="figures px-4 py-2.5 text-right text-muted">
                    {formatMoney(asset.accumulated_depreciation)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Money value={asset.book_value} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                    {asset.months_remaining > 0 ? `${asset.months_remaining} meses` : 'Ya depreciado'}
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Lo que debes</p>
              <Money
                value={loanSummary.data?.outstanding ?? 0}
                size="lg"
                tone={Number(loanSummary.data?.outstanding ?? 0) > 0 ? 'neg' : 'ink'}
              />
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Compromiso mensual</p>
              <Money value={loanSummary.data?.monthly_commitment ?? 0} size="lg" />
              <p className="mt-1 text-xs text-muted">Suma de las cuotas de tus créditos vigentes</p>
            </Card>
          </div>

          {loans.length === 0 ? (
            <EmptyState
              title="Sin préstamos registrados"
              message="Registra tus créditos para que ARCA separe cuánto de cada pago baja la deuda y cuánto es interés. Sin eso, un crédito distorsiona tu resultado."
              action={<Button onClick={() => setLoanModal(true)}>Nuevo préstamo</Button>}
            />
          ) : (
            <Table
              headers={[
                'Préstamo',
                'Desde',
                <span key="p" className="block text-right">
                  Original
                </span>,
                <span key="o" className="block text-right">
                  Debes hoy
                </span>,
                <span key="c" className="block text-right">
                  Cuota
                </span>,
                '',
              ]}
              secondary={[2, 3]}
            >
              {loans.map((loan) => (
                <tr key={loan.id} className="hover:bg-surface-2/50">
                  <td className="px-4 py-2.5">
                    <div className="font-medium">{loan.lender}</div>
                    <div className="text-xs text-muted">
                      {loan.description} · {(Number(loan.annual_rate) * 100).toFixed(1)}% anual
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                    {formatDate(loan.start_date)}
                  </td>
                  <td className="figures px-4 py-2.5 text-right text-muted">
                    {formatMoney(loan.principal)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Money value={loan.outstanding} tone={loan.status === 'PAID' ? 'muted' : 'ink'} />
                  </td>
                  <td className="figures px-4 py-2.5 text-right">
                    {formatMoney(loan.monthly_payment)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <div className="flex justify-end gap-1.5">
                      <Button
                        variant="ghost"
                        className="!px-2 !py-1 text-xs"
                        onClick={() => setScheduleFor(loan)}
                      >
                        Tabla
                      </Button>
                      {loan.status === 'ACTIVE' ? (
                        <Button
                          variant="secondary"
                          className="!px-2.5 !py-1 text-xs"
                          onClick={() => {
                            setPayTarget(loan)
                            setPayForm({
                              amount: String(loan.monthly_payment),
                              financial_account_id:
                                loan.financial_account_id ?? accountOptions[0]?.value ?? '',
                              date: today(),
                            })
                          }}
                        >
                          Registrar pago
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </Table>
          )}
        </div>
      )}

      <Modal title="Nuevo activo fijo" open={assetModal} onClose={() => setAssetModal(false)}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            createAsset.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <TextInput
            label="¿Qué compraste?"
            placeholder="MacBook Pro del equipo de diseño"
            value={assetForm.name}
            onChange={(event) => setAssetForm({ ...assetForm, name: event.target.value })}
            required
          />
          <SelectInput
            label="Tipo"
            value={assetForm.category}
            onChange={(event) => {
              const category = event.target.value
              const suggested = ASSET_CATEGORIES.find((c) => c.value === category)
              setAssetForm({
                ...assetForm,
                category,
                useful_life_months: String(suggested?.months ?? 60),
              })
            }}
            options={ASSET_CATEGORIES.map((c) => ({ value: c.value, label: c.label }))}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Costo sin IVA"
              type="number"
              step="0.01"
              value={assetForm.cost}
              onChange={(event) => setAssetForm({ ...assetForm, cost: event.target.value })}
              required
            />
            <TextInput
              label="IVA (opcional)"
              type="number"
              step="0.01"
              value={assetForm.tax_amount}
              onChange={(event) => setAssetForm({ ...assetForm, tax_amount: event.target.value })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Fecha de compra"
              type="date"
              value={assetForm.acquisition_date}
              onChange={(event) =>
                setAssetForm({ ...assetForm, acquisition_date: event.target.value })
              }
              required
            />
            <TextInput
              label="¿Cuántos meses te va a durar?"
              type="number"
              value={assetForm.useful_life_months}
              onChange={(event) =>
                setAssetForm({ ...assetForm, useful_life_months: event.target.value })
              }
              required
            />
          </div>
          <SelectInput
            label="¿Con qué lo pagaste?"
            value={assetForm.financial_account_id}
            onChange={(event) =>
              setAssetForm({ ...assetForm, financial_account_id: event.target.value })
            }
            options={[{ value: '', label: 'Todavía no lo pago' }, ...accountOptions]}
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setAssetModal(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createAsset.isPending}>
              Guardar activo
            </Button>
          </div>
        </form>
      </Modal>

      <Modal title="Nuevo préstamo" open={loanModal} onClose={() => setLoanModal(false)}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            createLoan.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <TextInput
            label="¿Quién te prestó?"
            placeholder="BBVA"
            value={loanForm.lender}
            onChange={(event) => setLoanForm({ ...loanForm, lender: event.target.value })}
            required
          />
          <TextInput
            label="¿Para qué?"
            placeholder="Capital de trabajo"
            value={loanForm.description}
            onChange={(event) => setLoanForm({ ...loanForm, description: event.target.value })}
            required
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Monto prestado"
              type="number"
              step="0.01"
              value={loanForm.principal}
              onChange={(event) => setLoanForm({ ...loanForm, principal: event.target.value })}
              required
            />
            <TextInput
              label="Tasa anual (0.24 = 24%)"
              type="number"
              step="0.0001"
              value={loanForm.annual_rate}
              onChange={(event) => setLoanForm({ ...loanForm, annual_rate: event.target.value })}
              required
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Plazo en meses"
              type="number"
              value={loanForm.term_months}
              onChange={(event) => setLoanForm({ ...loanForm, term_months: event.target.value })}
              required
            />
            <TextInput
              label="Primer pago desde"
              type="date"
              value={loanForm.start_date}
              onChange={(event) => setLoanForm({ ...loanForm, start_date: event.target.value })}
              required
            />
          </div>
          <SelectInput
            label="¿A qué cuenta entró el dinero?"
            value={loanForm.financial_account_id}
            onChange={(event) =>
              setLoanForm({ ...loanForm, financial_account_id: event.target.value })
            }
            options={[{ value: '', label: 'No entró a una cuenta' }, ...accountOptions]}
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setLoanModal(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createLoan.isPending}>
              Guardar préstamo
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        title={`Registrar pago · ${payTarget?.lender ?? ''}`}
        open={payTarget !== null}
        onClose={() => setPayTarget(null)}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            payLoan.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <p className="text-sm text-muted">
            ARCA separa sola cuánto de este pago baja la deuda y cuánto es interés.
          </p>
          <TextInput
            label="¿Cuánto pagaste?"
            type="number"
            step="0.01"
            value={payForm.amount}
            onChange={(event) => setPayForm({ ...payForm, amount: event.target.value })}
            required
          />
          <SelectInput
            label="¿Desde qué cuenta?"
            value={payForm.financial_account_id}
            onChange={(event) =>
              setPayForm({ ...payForm, financial_account_id: event.target.value })
            }
            options={accountOptions}
            required
          />
          <TextInput
            label="Fecha"
            type="date"
            value={payForm.date}
            onChange={(event) => setPayForm({ ...payForm, date: event.target.value })}
            required
          />
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setPayTarget(null)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={payLoan.isPending}>
              Registrar pago
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        title={`Tabla de amortización · ${scheduleFor?.lender ?? ''}`}
        open={scheduleFor !== null}
        onClose={() => setScheduleFor(null)}
      >
        {scheduleQuery.data ? (
          <div>
            <p className="mb-3 text-sm text-muted">
              Cuota de {formatMoney(scheduleQuery.data.monthly_payment)} al mes. Con el tiempo, la
              misma cuota paga menos interés y más deuda.
            </p>
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-surface">
                  <tr className="text-[11px] uppercase tracking-wider text-muted">
                    <th className="pb-1.5 text-left font-semibold">Vence</th>
                    <th className="pb-1.5 text-right font-semibold">Pago</th>
                    <th className="pb-1.5 text-right font-semibold">Deuda</th>
                    <th className="pb-1.5 text-right font-semibold">Interés</th>
                    <th className="pb-1.5 text-right font-semibold">Te queda</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {scheduleQuery.data.rows.map((row) => (
                    <tr key={row.number}>
                      <td className="whitespace-nowrap py-1.5 text-muted">
                        {formatDate(row.due_date)}
                      </td>
                      <td className="figures py-1.5 text-right">{formatMoney(row.payment)}</td>
                      <td className="figures py-1.5 text-right">{formatMoney(row.principal)}</td>
                      <td className="figures py-1.5 text-right text-muted">
                        {formatMoney(row.interest)}
                      </td>
                      <td className="figures py-1.5 text-right">{formatMoney(row.balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="h-32 animate-pulse rounded-lg bg-surface-2" />
        )}
      </Modal>
    </div>
  )
}
