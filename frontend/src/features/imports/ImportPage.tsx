/** Importar: el reporte de ventas de Toronja o un Excel/CSV de ingresos, gastos
 *  o efectivo. Antes de registrar nada se ve qué entra, qué está mal y qué ya
 *  estaba; confirmar crea todas las operaciones o ninguna. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, Receipt, TrendingDown, TrendingUp, Upload, Wallet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput } from '@/components/ui/Field'
import { PageHeader } from '@/components/ui/PageHeader'
import { TableFooter } from '@/components/ui/Pagination'
import { Segmented } from '@/components/ui/Segmented'
import { Card, Table } from '@/components/ui/Table'
import { formatDate, formatMoney } from '@/lib/format'
import { useAccounts, useCategories, useDimensions } from '@/lib/hooks'
import type { ImportBatch, ImportBatchDetail, ImportKind, ImportRow, ImportRowStatus, Page } from '@/types/api'

const PAGE_SIZE = 50

const KINDS: { key: ImportKind; label: string; description: string; icon: LucideIcon; accept: string }[] = [
  {
    key: 'TORONJA',
    label: 'Ventas de Toronja',
    description: 'El reporte de ventas que exporta Toronja (.xls). Cada ticket cae en su unidad y su forma de pago.',
    icon: Receipt,
    accept: '.xls,.html,.htm',
  },
  {
    key: 'INCOMES',
    label: 'Ingresos',
    description: 'Un Excel o CSV con lo que cobraste: fecha, concepto, monto y, si quieres, categoría y cuenta.',
    icon: TrendingUp,
    accept: '.csv,.xlsx,.txt',
  },
  {
    key: 'EXPENSES',
    label: 'Gastos',
    description: 'Un Excel o CSV con lo que pagaste: fecha, concepto, monto y, si quieres, categoría y cuenta.',
    icon: TrendingDown,
    accept: '.csv,.xlsx,.txt',
  },
  {
    key: 'CASH',
    label: 'Efectivo',
    description: 'El control de caja en Excel: entradas y salidas, o una sola columna con signo.',
    icon: Wallet,
    accept: '.csv,.xlsx,.txt',
  },
]
const KIND_LABELS: Record<ImportKind, string> = Object.fromEntries(KINDS.map((k) => [k.key, k.label])) as Record<
  ImportKind,
  string
>

const ROW_STATUS: Record<ImportRowStatus, { label: string; className: string }> = {
  OK: { label: 'Se creará', className: 'bg-pos/10 text-pos' },
  CREATED: { label: 'Creada', className: 'bg-pos/10 text-pos' },
  ERROR: { label: 'Error', className: 'bg-neg/10 text-neg' },
  DUPLICATE: { label: 'Duplicada', className: 'bg-warn/10 text-warn' },
  SKIPPED: { label: 'Omitida', className: 'bg-muted/10 text-muted' },
}
const BATCH_STATUS: Record<string, string> = { PREVIEW: 'Vista previa', CONFIRMED: 'Importada', DISCARDED: 'Descartada' }

function RowStatus({ status }: { status: ImportRowStatus }) {
  const config = ROW_STATUS[status] ?? { label: status, className: 'bg-muted/10 text-muted' }
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${config.className}`}>{config.label}</span>
}

function text(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

function money(value: unknown): string {
  const numeric = Number(value ?? 0)
  return numeric === 0 ? '—' : formatMoney(numeric)
}

export function ImportPage() {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState<ImportKind>('TORONJA')
  const [file, setFile] = useState<File | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<'' | ImportRowStatus>('')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const history = useQuery({
    queryKey: ['imports', 'list'],
    queryFn: async () => (await api.get<Page<ImportBatch>>('/imports?limit=20')).data,
  })

  const detail = useQuery({
    queryKey: ['imports', batchId, statusFilter, offset],
    queryFn: async () =>
      (
        await api.get<ImportBatchDetail>(`/imports/${batchId}`, {
          params: { status: statusFilter || undefined, limit: PAGE_SIZE, offset },
        })
      ).data,
    enabled: batchId !== null,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['imports'] })
  }

  const uploadMutation = useMutation({
    mutationFn: async ({ chosen, sheet }: { chosen: File; sheet?: string }) => {
      const form = new FormData()
      form.append('file', chosen)
      form.append('kind', kind)
      if (sheet) form.append('sheet', sheet)
      return (await api.post<ImportBatchDetail>('/imports', form, { timeout: 120000 })).data
    },
    onSuccess: (created) => {
      setError(null)
      setStatusFilter('')
      setOffset(0)
      setBatchId(created.id)
      invalidate()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const confirmMutation = useMutation({
    mutationFn: async (id: string) => (await api.post<ImportBatchDetail>(`/imports/${id}/confirm`, null, { timeout: 120000 })).data,
    onSuccess: () => {
      setError(null)
      setStatusFilter('')
      setOffset(0)
      invalidate()
      // Las operaciones recién creadas deben aparecer en Ingresos, Gastos, Por cobrar y Cuentas.
      void queryClient.invalidateQueries({ queryKey: ['income'] })
      void queryClient.invalidateQueries({ queryKey: ['expenses'] })
      void queryClient.invalidateQueries({ queryKey: ['receivables'] })
      void queryClient.invalidateQueries({ queryKey: ['accounts'] })
      void queryClient.invalidateQueries({ queryKey: ['customers'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const discardMutation = useMutation({
    mutationFn: async (id: string) => (await api.post<ImportBatch>(`/imports/${id}/discard`)).data,
    onSuccess: () => {
      setError(null)
      setBatchId(null)
      setFile(null)
      invalidate()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function chooseFile(chosen: File | null) {
    if (!chosen) return
    setFile(chosen)
    uploadMutation.mutate({ chosen })
  }

  function startOver() {
    setBatchId(null)
    setFile(null)
    setError(null)
    setStatusFilter('')
    setOffset(0)
  }

  const batch = detail.data
  const selectedKind = KINDS.find((k) => k.key === kind) ?? KINDS[0]
  const hasHistory = (history.data?.total ?? 0) > 0

  return (
    <div>
      <PageHeader
        title="Importar"
        description="Sube un archivo, revisa qué entra y confirma. Nada se registra hasta que tú lo digas."
        actions={
          batchId ? (
            <Button variant="secondary" onClick={startOver}>
              Subir otro archivo
            </Button>
          ) : null
        }
      />

      {batchId === null ? (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {KINDS.map((option) => {
              const Icon = option.icon
              const active = option.key === kind
              return (
                <Card
                  key={option.key}
                  onClick={() => setKind(option.key)}
                  className={`cursor-pointer transition-colors ${active ? 'border-accent ring-1 ring-accent' : 'hover:bg-surface-2'}`}
                >
                  <Icon className={`h-5 w-5 ${active ? 'text-accent' : 'text-muted'}`} />
                  <h3 className="mt-3 font-display text-base font-semibold">{option.label}</h3>
                  <p className="mt-1 text-xs text-muted">{option.description}</p>
                </Card>
              )
            })}
          </div>

          <input
            ref={fileInput}
            type="file"
            accept={selectedKind.accept}
            className="hidden"
            onChange={(event) => {
              chooseFile(event.target.files?.[0] ?? null)
              event.target.value = ''
            }}
          />
          <div
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              chooseFile(event.dataTransfer.files?.[0] ?? null)
            }}
          >
            {uploadMutation.isPending ? (
              <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface px-6 py-14 text-center">
                <Upload className="h-6 w-6 animate-pulse text-accent" />
                <p className="mt-3 text-sm text-muted">Leyendo {file?.name ?? 'el archivo'}…</p>
              </div>
            ) : (
              <EmptyState
                title={hasHistory ? `Suelta aquí ${selectedKind.label.toLowerCase()}` : 'Tu primera importación'}
                message="Sube el reporte de ventas de Toronja o un Excel de gastos; antes de registrar nada vas a ver qué entra."
                action={
                  <Button onClick={() => fileInput.current?.click()}>
                    <Upload className="h-4 w-4" /> Elegir archivo
                  </Button>
                }
              />
            )}
          </div>
          {error ? <p className="text-sm text-neg">{error}</p> : null}

          {hasHistory ? (
            <HistoryTable page={history.data!} onOpen={(id) => { setBatchId(id); setOffset(0); setStatusFilter('') }} />
          ) : null}
        </div>
      ) : detail.isLoading || !batch ? (
        <div className="h-40 animate-pulse rounded-xl bg-surface-2" />
      ) : (
        <BatchView
          batch={batch}
          statusFilter={statusFilter}
          onFilter={(next) => {
            setStatusFilter(next)
            setOffset(0)
          }}
          onOffset={setOffset}
          error={error}
          onError={setError}
          confirming={confirmMutation.isPending}
          onConfirm={() => confirmMutation.mutate(batch.id)}
          onDiscard={() => {
            if (window.confirm('¿Descartar esta importación? No se registrará nada.')) discardMutation.mutate(batch.id)
          }}
          onResheet={(sheet) => (file ? uploadMutation.mutate({ chosen: file, sheet }) : undefined)}
          canResheet={file !== null}
        />
      )}
    </div>
  )
}

// --- Historial ------------------------------------------------------------------

function HistoryTable({ page, onOpen }: { page: Page<ImportBatch>; onOpen: (id: string) => void }) {
  return (
    <div>
      <h2 className="mb-2 font-display text-base font-semibold">Importaciones anteriores</h2>
      <Table headers={['Archivo', 'Formato', 'Fecha', 'Creadas', 'Estado']} secondary={[2]}>
        {page.items.map((item) => (
          <tr key={item.id} className="cursor-pointer hover:bg-surface-2" onClick={() => onOpen(item.id)}>
            <td className="px-4 py-2.5 font-medium">{item.filename}</td>
            <td className="px-4 py-2.5 text-muted">{KIND_LABELS[item.kind]}</td>
            <td className="px-4 py-2.5 text-muted">{formatDate(item.created_at)}</td>
            <td className="figures px-4 py-2.5">
              {item.status === 'CONFIRMED' ? item.summary.created ?? 0 : `${item.summary.ok ?? 0} por crear`}
            </td>
            <td className="px-4 py-2.5 text-muted">{BATCH_STATUS[item.status] ?? item.status}</td>
          </tr>
        ))}
      </Table>
    </div>
  )
}

// --- Vista previa de un lote --------------------------------------------------------

function BatchView({
  batch,
  statusFilter,
  onFilter,
  onOffset,
  error,
  onError,
  confirming,
  onConfirm,
  onDiscard,
  onResheet,
  canResheet,
}: {
  batch: ImportBatchDetail
  statusFilter: '' | ImportRowStatus
  onFilter: (status: '' | ImportRowStatus) => void
  onOffset: (offset: number) => void
  error: string | null
  onError: (message: string | null) => void
  confirming: boolean
  onConfirm: () => void
  onDiscard: () => void
  onResheet: (sheet: string) => void
  canResheet: boolean
}) {
  const summary = batch.summary
  const isGeneric = batch.kind !== 'TORONJA'
  const needsMapping = isGeneric && !batch.mapping.fecha
  const preview = batch.status === 'PREVIEW'
  const operations = summary.operations ?? summary.ok ?? 0
  const sheets = batch.options.sheets ?? []

  const filterOptions: { key: '' | ImportRowStatus; label: string }[] = [
    { key: '', label: `Todas (${summary.rows ?? 0})` },
    ...(batch.status === 'CONFIRMED'
      ? [{ key: 'CREATED' as const, label: `Creadas (${summary.created ?? 0})` }]
      : [{ key: 'OK' as const, label: `A crear (${summary.ok ?? 0})` }]),
    { key: 'ERROR', label: `Errores (${summary.errors ?? 0})` },
    { key: 'DUPLICATE', label: `Duplicadas (${summary.duplicates ?? 0})` },
    { key: 'SKIPPED', label: `Omitidas (${summary.skipped ?? 0})` },
  ]

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-muted" />
              <h2 className="font-display text-lg font-semibold">{batch.filename}</h2>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">{KIND_LABELS[batch.kind]}</span>
              {batch.status !== 'PREVIEW' ? (
                <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">{BATCH_STATUS[batch.status]}</span>
              ) : null}
            </div>
            {sheets.length > 1 && preview ? (
              <div className="mt-2 max-w-xs">
                <SelectInput
                  label="Hoja"
                  options={sheets.map((sheet) => ({ value: sheet, label: sheet }))}
                  value={batch.options.sheet ?? sheets[0]}
                  disabled={!canResheet}
                  onChange={(event) => onResheet(event.target.value)}
                />
              </div>
            ) : null}
          </div>
          {preview ? (
            <div className="flex items-center gap-2">
              <Button variant="ghost" onClick={onDiscard}>
                Descartar
              </Button>
              <Button onClick={onConfirm} disabled={confirming || operations === 0 || needsMapping}>
                {confirming
                  ? 'Importando…'
                  : `Importar ${operations} ${operations === 1 ? 'operación' : 'operaciones'}`}
              </Button>
            </div>
          ) : null}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label={batch.status === 'CONFIRMED' ? 'Creadas' : 'A crear'} value={batch.status === 'CONFIRMED' ? summary.created ?? 0 : operations} tone="pos" />
          <Stat label="Errores" value={summary.errors ?? 0} tone={summary.errors ? 'neg' : 'muted'} />
          <Stat label="Duplicadas" value={summary.duplicates ?? 0} tone={summary.duplicates ? 'warn' : 'muted'} />
          <Stat label="Omitidas" value={summary.skipped ?? 0} tone="muted" />
        </div>

        {batch.status === 'CONFIRMED' ? <ResultLinks batch={batch} /> : null}
        {batch.status === 'PREVIEW' && (summary.ok ?? 0) === 0 && !needsMapping ? (
          <p className="mt-4 text-sm text-muted">
            {summary.duplicates ? 'Todo lo de este archivo ya estaba registrado: no hay nada nuevo que importar.' : 'No hay filas listas para importar. Revisa los errores.'}
          </p>
        ) : null}
        {error ? <p className="mt-4 text-sm text-neg">{error}</p> : null}
      </Card>

      {isGeneric && preview ? <MappingPanel batch={batch} onError={onError} /> : null}

      <div className="space-y-3">
        <Segmented options={filterOptions} value={statusFilter} onChange={onFilter} size="sm" />
        <RowsTable batch={batch} onOffset={onOffset} />
      </div>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'pos' | 'neg' | 'warn' | 'muted' }) {
  const tones = { pos: 'text-pos', neg: 'text-neg', warn: 'text-warn', muted: 'text-muted' }
  return (
    <div className="rounded-lg bg-surface-2 px-3 py-2.5">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className={`figures mt-0.5 text-xl font-semibold ${tones[tone]}`}>{value}</div>
    </div>
  )
}

function ResultLinks({ batch }: { batch: ImportBatchDetail }) {
  const { from, to } = batch.summary
  const range = from && to ? `?desde=${from}&hasta=${to}` : ''
  const links: { to: string; label: string }[] = []
  if (batch.kind === 'TORONJA' || batch.kind === 'INCOMES' || batch.kind === 'CASH') links.push({ to: `/ingresos${range}`, label: 'Ver ingresos' })
  if (batch.kind === 'EXPENSES' || batch.kind === 'CASH') links.push({ to: `/gastos${range}`, label: 'Ver gastos' })
  if (batch.kind === 'TORONJA') links.push({ to: '/por-cobrar?q=Adeudos%20Toronja', label: 'Ver adeudos por cobrar' })
  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
      <span className="text-muted">
        Listo. {batch.summary.created ?? 0} {batch.summary.created === 1 ? 'operación registrada' : 'operaciones registradas'}
        {from && to ? ` del ${formatDate(from)} al ${formatDate(to)}` : ''}.
      </span>
      {links.map((link) => (
        <Link key={link.to} to={link.to} className="font-medium text-accent hover:underline">
          {link.label} →
        </Link>
      ))}
    </div>
  )
}

// --- Mapeo de columnas (genérico) -----------------------------------------------------

const GUESSES: Record<string, string[]> = {
  fecha: ['fecha', 'date', 'dia', 'día'],
  concepto: ['concepto', 'descripcion', 'descripción', 'detalle', 'description'],
  monto: ['monto', 'importe', 'total', 'amount', 'cantidad'],
  ingreso: ['ingreso', 'entrada', 'entradas', 'ingresos', 'abono'],
  egreso: ['egreso', 'salida', 'salidas', 'egresos', 'cargo', 'gasto'],
  categoria: ['categoria', 'categoría', 'rubro', 'tipo'],
  cuenta: ['cuenta', 'caja', 'banco'],
  unidad: ['unidad', 'sucursal', 'vendedor'],
  contribuyente: ['contribuyente', 'rfc', 'razon social', 'razón social'],
  referencia: ['referencia', 'folio', 'ref'],
  forma_pago: ['forma de pago', 'forma_pago', 'metodo', 'método', 'pago'],
}

function guessMapping(columns: string[]): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [field, names] of Object.entries(GUESSES)) {
    const hit = columns.find((column) => names.includes(column.trim().toLowerCase()))
    if (hit && !Object.values(result).includes(hit)) result[field] = hit
  }
  return result
}

function MappingPanel({ batch, onError }: { batch: ImportBatchDetail; onError: (message: string | null) => void }) {
  const queryClient = useQueryClient()
  const columns = batch.options.columns ?? []
  const { data: accounts } = useAccounts()
  const { data: incomeCategories } = useCategories('INCOME')
  const { data: expenseCategories } = useCategories('EXPENSE')
  const { activeUnits, hasUnits } = useDimensions()
  const [twoColumns, setTwoColumns] = useState(Boolean(batch.mapping.ingreso))
  const [mapping, setMapping] = useState<Record<string, string>>(() =>
    Object.keys(batch.mapping).length ? batch.mapping : guessMapping(columns),
  )
  const [defaults, setDefaults] = useState<Record<string, string>>(batch.options.defaults ?? {})

  useEffect(() => {
    if (Object.keys(batch.mapping).length) setMapping(batch.mapping)
    setDefaults(batch.options.defaults ?? {})
  }, [batch.id, batch.mapping, batch.options.defaults])

  const mapMutation = useMutation({
    mutationFn: async () => {
      const cleanMapping = { ...mapping }
      if (batch.kind === 'CASH' && twoColumns) delete cleanMapping.monto
      else {
        delete cleanMapping.ingreso
        delete cleanMapping.egreso
      }
      return (await api.post<ImportBatchDetail>(`/imports/${batch.id}/map`, { mapping: cleanMapping, defaults })).data
    },
    onSuccess: () => {
      onError(null)
      void queryClient.invalidateQueries({ queryKey: ['imports'] })
    },
    onError: (err) => onError(errorMessage(err)),
  })

  const columnOptions = columns.map((column) => ({ value: column, label: column }))
  const accountOptions = (accounts ?? [])
    .filter((account) => account.active && (batch.kind !== 'CASH' || account.type === 'CASH'))
    .map((account) => ({ value: account.id, label: account.name }))
  const toOptions = (items: { id: string; name: string }[] | undefined) =>
    (items ?? []).map((item) => ({ value: item.id, label: item.name }))

  const fields: { key: string; label: string; required?: boolean }[] = [
    { key: 'fecha', label: 'Fecha', required: true },
    { key: 'concepto', label: 'Concepto', required: true },
    ...(batch.kind === 'CASH' && twoColumns
      ? [
          { key: 'ingreso', label: 'Entradas', required: true },
          { key: 'egreso', label: 'Salidas', required: true },
        ]
      : [{ key: 'monto', label: batch.kind === 'CASH' ? 'Monto (con signo)' : 'Monto', required: true }]),
    { key: 'categoria', label: 'Categoría (opcional)' },
    { key: 'cuenta', label: 'Cuenta de dinero (opcional)' },
    ...(hasUnits ? [{ key: 'unidad', label: 'Unidad (opcional)' }] : []),
    { key: 'contribuyente', label: 'Contribuyente (opcional)' },
    { key: 'referencia', label: 'Referencia (opcional)' },
    { key: 'forma_pago', label: 'Forma de pago (opcional)' },
  ]

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-base font-semibold">¿Qué columna es qué?</h3>
          <p className="mt-1 text-sm text-muted">
            Columnas detectadas: <span className="figures">{columns.length}</span>. Lo que no mapees se ignora.
          </p>
        </div>
        {batch.kind === 'CASH' ? (
          <Segmented
            size="sm"
            options={[
              { key: 'one', label: 'Una columna con signo' },
              { key: 'two', label: 'Entradas y salidas' },
            ]}
            value={twoColumns ? 'two' : 'one'}
            onChange={(key) => setTwoColumns(key === 'two')}
          />
        ) : null}
      </div>
      <form
        className="mt-4 space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          mapMutation.mutate()
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {fields.map((field) => (
            <SelectInput
              key={field.key}
              label={field.label}
              required={field.required}
              placeholder="—"
              options={columnOptions}
              value={mapping[field.key] ?? ''}
              onChange={(event) => setMapping({ ...mapping, [field.key]: event.target.value })}
            />
          ))}
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">Para todo el lote, si el archivo no lo trae</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {batch.kind === 'CASH' ? (
              <>
                <SelectInput
                  label="Categoría de las entradas"
                  placeholder="—"
                  options={toOptions(incomeCategories)}
                  value={defaults.income_category_id ?? ''}
                  onChange={(event) => setDefaults({ ...defaults, income_category_id: event.target.value })}
                />
                <SelectInput
                  label="Categoría de las salidas"
                  placeholder="—"
                  options={toOptions(expenseCategories)}
                  value={defaults.expense_category_id ?? ''}
                  onChange={(event) => setDefaults({ ...defaults, expense_category_id: event.target.value })}
                />
              </>
            ) : (
              <SelectInput
                label="Categoría"
                placeholder="—"
                options={toOptions(batch.kind === 'INCOMES' ? incomeCategories : expenseCategories)}
                value={defaults.category_id ?? ''}
                onChange={(event) => setDefaults({ ...defaults, category_id: event.target.value })}
              />
            )}
            <SelectInput
              label={batch.kind === 'CASH' ? 'Caja' : 'Cuenta de dinero'}
              placeholder="—"
              options={accountOptions}
              value={defaults.financial_account_id ?? ''}
              onChange={(event) => setDefaults({ ...defaults, financial_account_id: event.target.value })}
            />
            {hasUnits ? (
              <SelectInput
                label="Unidad"
                placeholder="—"
                options={activeUnits.map((unit) => ({ value: unit.id, label: unit.name }))}
                value={defaults.business_unit_id ?? ''}
                onChange={(event) => setDefaults({ ...defaults, business_unit_id: event.target.value })}
              />
            ) : null}
          </div>
        </div>
        <Button type="submit" variant="secondary" disabled={mapMutation.isPending}>
          {mapMutation.isPending ? 'Clasificando…' : 'Aplicar y revisar'}
        </Button>
      </form>
    </Card>
  )
}

// --- Filas -----------------------------------------------------------------------

function RowsTable({ batch, onOffset }: { batch: ImportBatchDetail; onOffset: (offset: number) => void }) {
  const rows = batch.rows
  const isToronja = batch.kind === 'TORONJA'
  const mapped = !isToronja && Boolean(batch.mapping.fecha)
  const rawColumns = useMemo(() => (batch.options.columns ?? []).slice(0, 5), [batch.options.columns])

  if (rows.total === 0) {
    return (
      <EmptyState
        title="Sin filas en este filtro"
        message="Cambia el filtro de arriba para ver el resto del archivo."
      />
    )
  }

  const headers = isToronja
    ? ['Folio', 'Fecha', 'Unidad', 'Efectivo', 'Tarjeta', 'Transferencia', 'Adeudo', 'Estado', 'Detalle']
    : mapped
      ? ['Fila', 'Fecha', 'Concepto', 'Monto', 'Categoría / Cuenta', 'Estado', 'Detalle']
      : ['Fila', ...rawColumns, 'Estado']

  return (
    <Table
      headers={headers}
      secondary={isToronja ? [5, 6, 9] : mapped ? [5, 7] : []}
      footer={<TableFooter page={rows} onOffsetChange={onOffset} noun="filas" />}
    >
      {rows.items.map((row) =>
        isToronja ? <ToronjaRow key={row.id} row={row} /> : mapped ? <MappedRow key={row.id} row={row} /> : <RawRow key={row.id} row={row} columns={rawColumns} />,
      )}
    </Table>
  )
}

function ToronjaRow({ row }: { row: ImportRow }) {
  const p = row.payload
  const card = p.card ?? Number(p.debit_card ?? 0) + Number(p.credit_card ?? 0)
  const owed = p.owed ?? Number(p.debt ?? 0) + Number(p.credit ?? 0)
  return (
    <tr className={row.status === 'ERROR' ? 'bg-neg/5' : undefined}>
      <td className="figures px-4 py-2.5">{text(p.folio)}</td>
      <td className="px-4 py-2.5 text-muted">{p.date ? formatDate(String(p.date)) : '—'}</td>
      <td className="px-4 py-2.5">{text(p.unit_name) || <span className="text-muted">{text(p.vendor)}</span>}</td>
      <td className="figures px-4 py-2.5 text-right">{money(p.cash)}</td>
      <td className="figures px-4 py-2.5 text-right">{money(card)}</td>
      <td className="figures px-4 py-2.5 text-right">{money(p.transfer)}</td>
      <td className="figures px-4 py-2.5 text-right">{money(owed)}</td>
      <td className="px-4 py-2.5">
        <RowStatus status={row.status} />
      </td>
      <td className="max-w-xs px-4 py-2.5 text-xs text-muted">{row.message ?? ''}</td>
    </tr>
  )
}

function MappedRow({ row }: { row: ImportRow }) {
  const p = row.payload
  const sign = p.direction === 'EXPENSE' ? '-' : ''
  return (
    <tr className={row.status === 'ERROR' ? 'bg-neg/5' : undefined}>
      <td className="figures px-4 py-2.5 text-muted">{row.row_number}</td>
      <td className="px-4 py-2.5 text-muted">{p.date ? formatDate(String(p.date)) : '—'}</td>
      <td className="max-w-xs truncate px-4 py-2.5">{text(p.description)}</td>
      <td className="figures px-4 py-2.5 text-right">{p.amount ? `${sign}${formatMoney(String(p.amount))}` : '—'}</td>
      <td className="px-4 py-2.5 text-xs text-muted">
        {[text(p.category_name), text(p.account_name), text(p.unit_name)].filter(Boolean).join(' · ') || '—'}
      </td>
      <td className="px-4 py-2.5">
        <RowStatus status={row.status} />
      </td>
      <td className="max-w-xs px-4 py-2.5 text-xs text-muted">{row.message ?? ''}</td>
    </tr>
  )
}

function RawRow({ row, columns }: { row: ImportRow; columns: string[] }) {
  const raw = (row.payload.raw ?? {}) as Record<string, unknown>
  return (
    <tr>
      <td className="figures px-4 py-2.5 text-muted">{row.row_number}</td>
      {columns.map((column) => (
        <td key={column} className="max-w-[12rem] truncate px-4 py-2.5">
          {text(raw[column])}
        </td>
      ))}
      <td className="px-4 py-2.5">
        <RowStatus status={row.status} />
      </td>
    </tr>
  )
}
