import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { formatMoney, formatMonthYear, formatWhole } from '@/lib/format'
import type { BranchCutStatus, DashboardBranchRow, DashboardBranches } from '@/types/api'
import { useGrowOnce } from './useCountUp'

const CUT: Record<BranchCutStatus, { label: string; className: string }> = {
  DELIVERED: { label: 'Corte de ayer entregado', className: 'bg-accent' },
  LATE: { label: 'Corte de ayer entregado tarde', className: 'bg-warn' },
  MISSING: { label: 'Falta el corte de ayer', className: 'bg-neg ring-[3px] ring-neg/25' },
  NA: { label: 'Sin caja: no aplica', className: 'bg-muted' },
}

function Sparkline({ points }: { points: DashboardBranchRow['sparkline'] }) {
  if (points.length < 2) return <span className="block h-[22px] w-[58px]" aria-hidden />
  const width = 58
  const height = 22
  const values = points.map((p) => Number(p.value))
  const max = Math.max(...values, 1)
  const step = (width - 8) / (points.length - 1)
  const coords = values.map((v, i) => [4 + i * step, 4 + (1 - v / max) * (height - 8)] as const)
  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const last = coords[coords.length - 1]
  const total = values.reduce((a, b) => a + b, 0)
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Últimos 30 días: ${formatMoney(total)}`}>
      <path d={`${line} L${last[0].toFixed(1)},${height} L4,${height} Z`} fill="var(--color-accent)" opacity={0.12} />
      <path d={line} fill="none" stroke="var(--color-accent)" strokeWidth={1.5} />
      <circle cx={last[0]} cy={last[1]} r={2.2} fill="var(--color-accent)" />
    </svg>
  )
}

function Delta({ row }: { row: DashboardBranchRow }) {
  if (row.delta_pct === null) return <span className="text-[11.5px] text-muted">sin base</span>
  const value = Number(row.delta_pct)
  const label = `${value > 0 ? '+' : value < 0 ? '−' : '='} ${Math.abs(value).toFixed(0)}%`
  const tone = value > 0 ? 'bg-accent/10 text-accent' : value < 0 ? 'bg-neg/10 text-neg' : 'text-muted'
  return (
    <span
      className={`figures rounded px-1.5 py-0.5 text-[11.5px] font-medium ${tone}`}
      title={row.delta_basis === 'avg_3m' ? 'Contra su promedio de los 3 meses previos' : 'Contra el mismo mes del año pasado'}
    >
      {label}
    </span>
  )
}

function monthLabel(iso: string | null): string {
  if (!iso) return ''
  const [year, month] = iso.split('-').map(Number)
  return formatMonthYear(new Date(year, month - 1, 1))
}

export function BranchesPanel({ branches, hasUnits }: { branches: DashboardBranches; hasUnits: boolean }) {
  const grown = useGrowOnce()
  const rows = branches.rows
  const anySales = rows.some((row) => Number(row.sales) > 0)
  const top = rows[0]
  // El encabezado de Δ dice contra qué se compara cuando todas las filas coinciden.
  const bases = new Set(rows.map((row) => row.delta_basis).filter(Boolean))
  const year = branches.month ? Number(branches.month.slice(0, 4)) : new Date().getFullYear()
  const deltaHeader = bases.size === 1 ? (bases.has('avg_3m') ? 'vs prom. 3 m' : `vs ${year - 1}`) : 'Δ'

  return (
    <section
      className="panel flex min-w-0 flex-col overflow-hidden p-4"
      aria-label={top ? `Sucursales: ${top.name} lidera con ${formatMoney(top.sales)}` : 'Sucursales'}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
        <h2 className="text-[13px] font-medium text-ink-soft">Sucursales</h2>
        {anySales ? (
          <span className="text-xs text-muted">
            {monthLabel(branches.month)}
            {branches.origin === 'historical' ? ' · histórico' : ''} · punto = corte de ayer
          </span>
        ) : null}
      </div>

      {!hasUnits ? (
        <div className="mt-4 flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 py-8 text-center">
          <p className="text-sm text-ink">Todavía no hay unidades de negocio</p>
          <p className="mt-1 text-xs text-muted">Da de alta tus sucursales para ver cuánto vende cada una y si entregó su corte.</p>
          <Link to="/configuracion" className="mt-4">
            <Button variant="secondary">Configurar unidades</Button>
          </Link>
        </div>
      ) : !anySales ? (
        <div className="mt-4 flex flex-1 flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 py-8 text-center">
          <p className="text-sm text-ink">Aún no hay ventas por sucursal</p>
          <p className="mt-1 text-xs text-muted">Importa el reporte de ventas o registra un ingreso con su unidad.</p>
          <Link to="/importar" className="mt-4">
            <Button variant="secondary">Importar ventas</Button>
          </Link>
        </div>
      ) : (
        <table className="mt-2 w-full table-fixed border-collapse text-[13px]">
          <thead>
            <tr className="text-left text-[11.5px] font-normal text-muted">
              <th className="px-1.5 py-1 font-normal">Sucursal</th>
              <th className="w-[80px] px-1.5 py-1 text-right font-normal">{branches.month ? monthLabel(branches.month).split(' ')[0] : 'Mes'}</th>
              <th className="w-[76px] whitespace-nowrap px-1.5 py-1 font-normal">{deltaHeader}</th>
              <th className="hidden w-[66px] px-1.5 py-1 font-normal lg:table-cell">30 días</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.business_unit_id} className="border-t border-border hover:bg-surface-2/60">
                <td className="px-1.5 py-1.5">
                  <Link to={`/ingresos?business_unit_id=${row.business_unit_id}`} className="block min-w-0 text-ink hover:text-accent">
                    <span className="flex items-center gap-2">
                      <span className={`inline-block h-[7px] w-[7px] shrink-0 rounded-full ${CUT[row.cut].className}`} title={CUT[row.cut].label} />
                      <span className="sr-only">{CUT[row.cut].label}. </span>
                      <span className="truncate">{row.name}</span>
                    </span>
                    {/* La barra de ranking vive bajo el nombre: no roba una columna. */}
                    <span className="mt-1 block h-1 w-full pl-[15px]">
                      <span
                        className="block h-1 rounded-sm bg-gradient-to-r from-accent-strong to-accent transition-[width] duration-500 ease-out"
                        style={{ width: grown ? `${Math.max(Number(row.share) * 100, Number(row.sales) > 0 ? 3 : 0)}%` : 0 }}
                      />
                    </span>
                  </Link>
                </td>
                <td className="figures whitespace-nowrap px-1.5 py-1.5 text-right align-top text-ink">{formatWhole(row.sales)}</td>
                <td className="whitespace-nowrap px-1.5 py-1.5 align-top">
                  <Delta row={row} />
                </td>
                <td className="hidden px-1.5 py-1 align-top lg:table-cell">
                  <Sparkline points={row.sparkline} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
