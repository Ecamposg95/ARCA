import { Link } from 'react-router-dom'
import { formatMoney } from '@/lib/format'
import type { DashboardApprovals } from '@/types/api'

/** Franja ámbar: sólo si hay algo por autorizar y quien mira puede autorizarlo. */
export function ApprovalStrip({ approvals, userName }: { approvals: DashboardApprovals; userName: string }) {
  if (!approvals.can_authorize || approvals.pending.length === 0) return null
  const [first] = approvals.pending
  const extra = approvals.pending.length - 1
  const firstName = userName.split(' ')[0]
  return (
    <Link
      to="/propuestas?fuente=approval"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-panel border border-warn/40 bg-warn/[0.06] px-4 py-2.5 text-[13px] hover:bg-warn/10"
    >
      <span className="font-medium text-warn">
        {approvals.pending.length === 1 ? '1 pago espera' : `${approvals.pending.length} pagos esperan`} a {firstName}
      </span>
      <span className="text-ink-soft">
        {first.summary}
        {first.amount && !first.summary.includes('$') ? ` · ${formatMoney(first.amount)}` : ''}
        {extra > 0 ? ` · y ${extra} más` : ''}
      </span>
      <span className="ml-auto font-medium text-accent">Revisar →</span>
    </Link>
  )
}
