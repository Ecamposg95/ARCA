import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { downloadErrorMessage, downloadFile } from '@/lib/download'

interface Preview {
  rfc: string | null
  rfc_ok: boolean
  accounts: number
  missing_accounts: { id: string; code: string; name: string }[]
  ready: boolean
}

/** Contabilidad electrónica del SAT (Anexo 24): catálogo y balanza del mes en XML. */
export function SatExport({
  period,
  title,
  onClose,
}: {
  period: { year: number; month: number } | null
  title: string
  onClose: () => void
}) {
  const [busy, setBusy] = useState<'catalogo' | 'balanza' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const preview = useQuery({
    queryKey: ['accounting', 'sat-preview', period?.year, period?.month],
    queryFn: async () =>
      (
        await api.get<Preview>('/accounting/sat/preview', {
          params: { year: period!.year, month: period!.month },
        })
      ).data,
    enabled: period !== null,
    staleTime: 0,
  })

  function close() {
    setError(null)
    onClose()
  }

  async function download(kind: 'catalogo' | 'balanza') {
    if (!period) return
    setBusy(kind)
    setError(null)
    try {
      await downloadFile(
        `/accounting/sat/${kind}`,
        { year: period.year, month: period.month },
        `${kind}-sat.xml`,
      )
    } catch (err) {
      setError(await downloadErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const data = preview.data
  const missing = data?.missing_accounts ?? []

  return (
    <Modal title={`Contabilidad electrónica de ${title}`} open={period !== null} onClose={close}>
      {preview.isLoading ? (
        <div className="h-24 animate-pulse rounded-lg bg-surface-2" />
      ) : preview.error ? (
        <p className="text-sm text-neg">{errorMessage(preview.error)}</p>
      ) : data ? (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted">RFC</dt>
              <dd className={`figures font-semibold ${data.rfc_ok ? '' : 'text-neg'}`}>
                {data.rfc ?? 'Sin capturar'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Cuentas en el catálogo</dt>
              <dd className="figures font-semibold">{data.accounts}</dd>
            </div>
          </dl>

          {!data.rfc_ok ? (
            <p className="rounded-lg border border-neg/30 bg-neg/10 p-3 text-sm text-neg">
              Falta el RFC de la empresa, o no tiene formato válido. Captúralo en{' '}
              <Link to="/configuracion" className="font-medium underline" onClick={close}>
                Configuración
              </Link>
              .
            </p>
          ) : null}

          {missing.length > 0 ? (
            <div className="rounded-lg border border-warn/30 bg-warn/10 p-3 text-sm">
              <p className="font-medium text-warn">
                {missing.length === 1
                  ? '1 cuenta sin código agrupador del SAT'
                  : `${missing.length} cuentas sin código agrupador del SAT`}
              </p>
              <p className="mt-1 text-muted">
                El SAT exige clasificar todas las cuentas. Asígnalo en el{' '}
                <Link
                  to="/contabilidad?vista=catalogo"
                  className="font-medium text-accent hover:underline"
                  onClick={close}
                >
                  catálogo de cuentas
                </Link>
                .
              </p>
              <ul className="figures mt-2 space-y-0.5 text-xs text-muted">
                {missing.map((account) => (
                  <li key={account.id}>
                    {account.code} {account.name}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <p className="text-xs text-muted">
            Los XML salen sin sellar. El sello con la e.firma y el envío al buzón tributario se
            hacen con la herramienta del contador.
          </p>

          {error ? (
            <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
              {error}
            </p>
          ) : null}

          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={close}>
              Cerrar
            </Button>
            <Button
              variant="secondary"
              disabled={!data.ready || busy !== null}
              onClick={() => void download('catalogo')}
            >
              {busy === 'catalogo' ? 'Preparando…' : 'Catálogo XML'}
            </Button>
            <Button disabled={!data.ready || busy !== null} onClick={() => void download('balanza')}>
              {busy === 'balanza' ? 'Preparando…' : 'Balanza XML'}
            </Button>
          </div>
        </div>
      ) : null}
    </Modal>
  )
}
