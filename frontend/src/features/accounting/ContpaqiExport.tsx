import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { downloadErrorMessage, downloadFile } from '@/lib/download'

interface Preview {
  entries: number
  movements: number
  unmapped_accounts: { id: string; code: string; name: string }[]
}

/** Exportar las pólizas de un mes para cargarlas en CONTPAQi Contabilidad. */
export function ContpaqiExport({
  period,
  title,
  onClose,
}: {
  period: { year: number; month: number } | null
  title: string
  onClose: () => void
}) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const preview = useQuery({
    queryKey: ['accounting', 'contpaqi-preview', period?.year, period?.month],
    queryFn: async () =>
      (
        await api.get<Preview>('/accounting/contpaqi/preview', {
          params: { year: period!.year, month: period!.month },
        })
      ).data,
    enabled: period !== null,
    // Las equivalencias pueden haber cambiado en el catálogo hace un momento.
    staleTime: 0,
  })

  async function download() {
    if (!period) return
    setDownloading(true)
    setError(null)
    try {
      await downloadFile(
        '/accounting/contpaqi',
        { year: period.year, month: period.month },
        'polizas-contpaqi.txt',
      )
    } catch (err) {
      setError(await downloadErrorMessage(err))
    } finally {
      setDownloading(false)
    }
  }

  const data = preview.data
  const unmapped = data?.unmapped_accounts ?? []

  return (
    <Modal
      title={`Pólizas de ${title} para CONTPAQi`}
      open={period !== null}
      onClose={() => {
        setError(null)
        onClose()
      }}
    >
      {preview.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2" />
      ) : preview.error ? (
        <p className="text-sm text-neg">{errorMessage(preview.error)}</p>
      ) : data ? (
        <div className="space-y-4">
          <p className="text-sm">
            <span className="figures font-semibold">{data.entries}</span>{' '}
            {data.entries === 1 ? 'póliza' : 'pólizas'} ·{' '}
            <span className="figures font-semibold">{data.movements}</span>{' '}
            {data.movements === 1 ? 'movimiento' : 'movimientos'}
          </p>

          {unmapped.length > 0 ? (
            <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-sm">
              <p className="font-medium text-warn">
                {unmapped.length === 1
                  ? '1 cuenta sin equivalente en CONTPAQi'
                  : `${unmapped.length} cuentas sin equivalente en CONTPAQi`}
              </p>
              <p className="mt-1 text-muted">
                Saldrán con su código de ARCA. Si en tu CONTPAQi tienen otro número, captúralo en
                el{' '}
                <Link
                  to="/contabilidad?vista=catalogo"
                  className="font-medium text-accent hover:underline"
                  onClick={onClose}
                >
                  catálogo de cuentas
                </Link>
                .
              </p>
              <ul className="figures mt-2 space-y-0.5 text-xs text-muted">
                {unmapped.map((account) => (
                  <li key={account.id}>
                    {account.code} {account.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-pos">Todas las cuentas del mes tienen su equivalente.</p>
          )}

          <p className="text-xs text-muted">
            Archivo de texto para "Cargado de pólizas" de CONTPAQi Contabilidad. Es un formato de
            referencia: haz la primera carga en una empresa de prueba.
          </p>

          {error ? (
            <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
              {error}
            </p>
          ) : null}

          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cerrar
            </Button>
            <Button onClick={() => void download()} disabled={downloading || data.entries === 0}>
              {downloading ? 'Preparando…' : 'Descargar archivo'}
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}
