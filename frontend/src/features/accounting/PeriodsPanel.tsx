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
import { Table } from '@/components/ui/Table'
import { formatMoney } from '@/lib/format'

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

export function PeriodsPanel() {
  const queryClient = useQueryClient()
  const [reopening, setReopening] = useState<Period | null>(null)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

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
            <td className="px-4 py-2.5 text-right">
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
