/** Cierre de periodo: proteger lo que ya se declaró.
 *
 *  Cerrar no congela la verdad: obliga a reabrir a propósito para cambiarla, y
 *  el motivo queda guardado. Sin esto, una corrección de hoy puede alterar en
 *  silencio una declaración de hace meses.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Card, Table } from '@/components/ui/Table'
import { ContpaqiExport } from '@/features/accounting/ContpaqiExport'
import { OpeningBalanceForm } from '@/features/accounting/OpeningBalanceForm'
import { SatExport } from '@/features/accounting/SatExport'
import { formatDate, formatMoney } from '@/lib/format'
import type { FiscalYear, LedgerAccount, OpeningBalance, Page } from '@/types/api'

interface Period {
  year: number
  month: number
  label: string
  entries: number
  movement: string
  closed: boolean
  can_close: boolean
}

function monthName(label: string) {
  const [year, month] = label.split('-').map(Number)
  const name = new Date(year, month - 1, 1).toLocaleDateString('es-MX', {
    month: 'long',
    year: 'numeric',
  })
  return name.charAt(0).toUpperCase() + name.slice(1)
}

/** Saldos iniciales: la puerta de entrada de una empresa que llega con historia. */
function OpeningBalanceCard({ onShowEntry }: { onShowEntry?: (id: string) => void }) {
  const [formOpen, setFormOpen] = useState(false)
  const accountsQuery = useQuery({
    queryKey: ['accounting', 'accounts'],
    queryFn: async () => (await api.get<LedgerAccount[]>('/accounting/accounts')).data,
  })
  const openingQuery = useQuery({
    queryKey: ['accounting', 'opening-balance'],
    queryFn: async () => (await api.get<OpeningBalance>('/accounting/opening-balance')).data,
  })
  const entry = openingQuery.data?.entry ?? null

  if (openingQuery.isLoading) return <div className="h-24 animate-pulse rounded-xl bg-surface-2" />

  return (
    <>
      <Card>
        {entry ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-base font-semibold">
                Saldos iniciales al {formatDate(entry.date)} · <span className="figures">{entry.folio}</span>
              </h3>
              <p className="mt-1 text-sm text-muted">
                Para corregirlos, revierte la póliza desde el diario y captura otra.
              </p>
            </div>
            {onShowEntry ? (
              <Button variant="secondary" onClick={() => onShowEntry(entry.id)}>
                Ver póliza
              </Button>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-base font-semibold">Saldos iniciales</h3>
              <p className="mt-1 text-sm text-muted">Trae los saldos con los que la empresa llega a ARCA.</p>
            </div>
            <Button onClick={() => setFormOpen(true)}>Capturar saldos iniciales</Button>
          </div>
        )}
      </Card>
      <OpeningBalanceForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        accounts={accountsQuery.data ?? []}
        onSaved={(saved) => {
          setFormOpen(false)
          onShowEntry?.(saved.id)
        }}
      />
    </>
  )
}

/** Ejercicios: cerrar un año traspasa ingresos y gastos a Resultados Acumulados
 *  y lo deja bajo candado; reabrirlo revierte esa póliza y pide motivo. */
function FiscalYears({ onShowEntry }: { onShowEntry?: (id: string) => void }) {
  const queryClient = useQueryClient()
  const [reopening, setReopening] = useState<FiscalYear | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const currentYear = new Date().getFullYear()

  const { data, isLoading } = useQuery({
    queryKey: ['periods', 'years'],
    queryFn: async () => (await api.get<Page<FiscalYear>>('/periods/years')).data.items,
  })

  // Cerrar o reabrir asienta una póliza: el diario y la balanza también cambian.
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['periods'] })
    void queryClient.invalidateQueries({ queryKey: ['accounting'] })
  }

  const close = useMutation({
    mutationFn: async (year: number) => {
      await api.post(`/periods/years/${year}/close`, { notes: null })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const reopen = useMutation({
    mutationFn: async () => {
      await api.post(`/periods/years/${reopening!.year}/reopen`, { reason })
    },
    onSuccess: () => {
      invalidate()
      setReopening(null)
      setReason('')
      setError(null)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (isLoading) return <div className="h-32 animate-pulse rounded-xl bg-surface-2" />

  return (
    <section className="space-y-3">
      <div>
        <h3 className="font-display text-base font-semibold">Ejercicios</h3>
        <p className="text-sm text-muted">
          Cerrar un ejercicio pasa su utilidad a Resultados Acumulados y lo deja bajo candado. Se cierran en orden,
          del más antiguo al más reciente.
        </p>
      </div>
      <Table
        headers={[
          'Año',
          <span key="i" className="block text-right">
            Ingresos
          </span>,
          <span key="g" className="block text-right">
            Gastos
          </span>,
          <span key="r" className="block text-right">
            Resultado
          </span>,
          'Estado',
          '',
        ]}
        secondary={[2, 3]}
      >
        {(data ?? []).map((item) => (
          <tr key={item.year} className="hover:bg-surface-2/50">
            <td className="figures px-4 py-2.5 font-medium">{item.year}</td>
            <td className="figures px-4 py-2.5 text-right text-muted">{formatMoney(item.revenue)}</td>
            <td className="figures px-4 py-2.5 text-right text-muted">{formatMoney(item.expenses)}</td>
            <td className={`figures px-4 py-2.5 text-right font-medium ${Number(item.result) < 0 ? 'text-neg' : ''}`}>
              {formatMoney(item.result)}
            </td>
            <td className="px-4 py-2.5">
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                  item.closed ? 'bg-pos/10 text-pos' : 'bg-surface-2 text-muted'
                }`}
              >
                {item.closed ? 'Cerrado' : 'Abierto'}
              </span>
            </td>
            <td className="whitespace-nowrap px-4 py-2.5 text-right">
              {item.closed ? (
                <>
                  {item.closing_entry_id && item.closing_folio && onShowEntry ? (
                    <Button
                      variant="ghost"
                      className="mr-1 !px-2 !py-1 text-xs"
                      title={item.closing_folio}
                      onClick={() => onShowEntry(item.closing_entry_id!)}
                    >
                      Ver póliza
                    </Button>
                  ) : null}
                  <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => setReopening(item)}>
                    Reabrir
                  </Button>
                </>
              ) : item.can_close ? (
                <Button
                  variant="secondary"
                  className="!px-2.5 !py-1 text-xs"
                  disabled={close.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `¿Cerrar el ejercicio ${item.year}? Ingresos y gastos pasan a Resultados Acumulados y el año queda bajo candado.`,
                      )
                    )
                      close.mutate(item.year)
                  }}
                >
                  Cerrar ejercicio
                </Button>
              ) : item.year >= currentYear ? (
                <span className="text-xs text-muted">Aún en curso</span>
              ) : item.blocked_by ? (
                <span className="text-xs text-muted">Cierra {item.blocked_by} primero</span>
              ) : null}
            </td>
          </tr>
        ))}
      </Table>

      <Modal
        title={`Reabrir el ejercicio ${reopening?.year ?? ''}`}
        open={reopening !== null}
        onClose={() => setReopening(null)}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            reopen.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <p className="text-sm text-muted">
            Reabrir revierte la póliza de cierre al 31 de diciembre: ingresos y gastos del año vuelven a quedar
            abiertos. Explica por qué; el motivo queda guardado junto con tu nombre.
          </p>
          <TextInput
            label="Motivo"
            placeholder="Faltó registrar una factura de diciembre"
            value={reason}
            minLength={3}
            maxLength={500}
            onChange={(event) => setReason(event.target.value)}
            required
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setReopening(null)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={reopen.isPending}>
              Reabrir ejercicio
            </Button>
          </div>
        </form>
      </Modal>
    </section>
  )
}

export function PeriodsPanel({ onShowEntry }: { onShowEntry?: (id: string) => void }) {

  const queryClient = useQueryClient()
  const [reopening, setReopening] = useState<Period | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<Period | null>(null)
  const [satPeriod, setSatPeriod] = useState<Period | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['periods'],
    queryFn: async () => (await api.get<{ items: Period[] }>('/periods')).data.items,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['periods'] })
  }

  const close = useMutation({
    mutationFn: async (period: Period) => {
      await api.post('/periods/close', { year: period.year, month: period.month })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const reopen = useMutation({
    mutationFn: async () => {
      await api.post('/periods/reopen', {
        year: reopening!.year,
        month: reopening!.month,
        reason,
      })
    },
    onSuccess: () => {
      invalidate()
      setReopening(null)
      setReason('')
      setError(null)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  if (isLoading) return <div className="h-48 animate-pulse rounded-xl bg-surface-2" />

  return (
    <div className="space-y-4">
      <OpeningBalanceCard onShowEntry={onShowEntry} />

      <FiscalYears onShowEntry={onShowEntry} />

      <p className="text-sm text-muted">
        Cierra los meses que ya declaraste. Un mes cerrado no acepta operaciones nuevas ni
        correcciones hasta que lo reabras a propósito.
      </p>

      <Table
        headers={[
          'Mes',
          <span key="p" className="block text-right">
            Pólizas
          </span>,
          <span key="m" className="block text-right">
            Movimiento
          </span>,
          'Estado',
          '',
        ]}
        secondary={[2, 3]}
      >
        {(data ?? []).map((period) => (
          <tr key={period.label} className="hover:bg-surface-2/50">
            <td className="px-4 py-2.5 font-medium">{monthName(period.label)}</td>
            <td className="figures px-4 py-2.5 text-right text-muted">{period.entries}</td>
            <td className="figures px-4 py-2.5 text-right text-muted">
              {formatMoney(period.movement)}
            </td>
            <td className="px-4 py-2.5">
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                  period.closed ? 'bg-pos/10 text-pos' : 'bg-surface-2 text-muted'
                }`}
              >
                {period.closed ? 'Cerrado' : 'Abierto'}
              </span>
            </td>
            <td className="whitespace-nowrap px-4 py-2.5 text-right">
              {period.entries > 0 ? (
                <>
                  <Button
                    variant="ghost"
                    className="mr-1 !px-2 !py-1 text-xs"
                    onClick={() => setExporting(period)}
                  >
                    CONTPAQi
                  </Button>
                  <Button
                    variant="ghost"
                    className="mr-1 !px-2 !py-1 text-xs"
                    onClick={() => setSatPeriod(period)}
                  >
                    SAT
                  </Button>
                </>
              ) : null}
              {period.closed ? (
                <Button
                  variant="ghost"
                  className="!px-2 !py-1 text-xs"
                  onClick={() => setReopening(period)}
                >
                  Reabrir
                </Button>
              ) : period.can_close ? (
                <Button
                  variant="secondary"
                  className="!px-2.5 !py-1 text-xs"
                  disabled={close.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `¿Cerrar ${monthName(period.label)}? No se podrán registrar ni corregir operaciones de ese mes.`,
                      )
                    )
                      close.mutate(period)
                  }}
                >
                  Cerrar mes
                </Button>
              ) : (
                <span className="text-xs text-muted">Aún en curso</span>
              )}
            </td>
          </tr>
        ))}
      </Table>

      <ContpaqiExport
        period={exporting}
        title={exporting ? monthName(exporting.label) : ''}
        onClose={() => setExporting(null)}
      />

      <SatExport
        period={satPeriod}
        title={satPeriod ? monthName(satPeriod.label) : ''}
        onClose={() => setSatPeriod(null)}
      />

      <Modal
        title={`Reabrir ${reopening ? monthName(reopening.label) : ''}`}
        open={reopening !== null}
        onClose={() => setReopening(null)}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault()
            reopen.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <p className="text-sm text-muted">
            Este mes ya se declaró. Explica por qué hay que reabrirlo: el motivo queda guardado
            junto con tu nombre.
          </p>
          <TextInput
            label="Motivo"
            placeholder="Faltó registrar la factura del proveedor"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setReopening(null)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={reopen.isPending}>
              Reabrir mes
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
