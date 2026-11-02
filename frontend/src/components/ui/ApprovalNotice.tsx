import { Link } from 'react-router-dom'
import { useCanAuthorize, usePendingCount } from '@/lib/approvals'

/** "N operaciones esperan autorización" con enlace a Propuestas. Sólo lo ve
 *  quien puede autorizar: a los demás no les sirve de nada. */
export function ApprovalNotice() {
  const canAuthorize = useCanAuthorize()
  const { data } = usePendingCount()
  const pending = data?.approval ?? 0
  if (!canAuthorize || pending === 0) return null
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-accent/30 bg-accent-soft px-4 py-2.5 text-sm">
      <span>
        <span className="figures font-semibold">{pending}</span>{' '}
        {pending === 1 ? 'operación espera' : 'operaciones esperan'} tu autorización.
      </span>
      <Link to="/propuestas?origen=autorizacion" className="text-xs font-medium text-accent underline">
        Ir a Propuestas
      </Link>
    </div>
  )
}
