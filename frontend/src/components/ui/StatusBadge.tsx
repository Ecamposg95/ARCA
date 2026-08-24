const LABELS: Record<string, { label: string; className: string }> = {
  PENDING: { label: 'Pendiente', className: 'bg-warn/10 text-warn' },
  PAID: { label: 'Pagado', className: 'bg-pos/10 text-pos' },
  CANCELLED: { label: 'Cancelado', className: 'bg-muted/10 text-muted' },
  ACTIVE: { label: 'Activo', className: 'bg-pos/10 text-pos' },
  INACTIVE: { label: 'Inactivo', className: 'bg-muted/10 text-muted' },
}

export function StatusBadge({ status, paidLabel }: { status: string; paidLabel?: string }) {
  const config = LABELS[status] ?? { label: status, className: 'bg-muted/10 text-muted' }
  const label = status === 'PAID' && paidLabel ? paidLabel : config.label
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${config.className}`}>
      {label}
    </span>
  )
}
