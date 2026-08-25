import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeftRight,
  BarChart3,
  BookOpen,
  Building2,
  CalendarClock,
  HandCoins,
  LayoutDashboard,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import { api } from '@/api/client'
import { ArcaMark } from '@/components/ui/ArcaMark'
import { AppFooter } from '@/components/layout/AppFooter'
import { AppHeader } from '@/components/layout/AppHeader'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  roles?: string[]
}

const NAV_SECTIONS: { label: string | null; items: NavItem[] }[] = [
  { label: null, items: [{ to: '/', label: 'Inicio', icon: LayoutDashboard }] },
  {
    label: 'Dinero',
    items: [
      { to: '/movimientos', label: 'Movimientos', icon: ArrowLeftRight },
      { to: '/cuentas', label: 'Cuentas', icon: Wallet },
    ],
  },
  {
    label: 'Ventas',
    items: [
      { to: '/ingresos', label: 'Ingresos', icon: TrendingUp },
      { to: '/por-cobrar', label: 'Por cobrar', icon: HandCoins },
      { to: '/clientes', label: 'Clientes', icon: Users },
    ],
  },
  {
    label: 'Gastos',
    items: [
      { to: '/gastos', label: 'Gastos', icon: TrendingDown },
      { to: '/por-pagar', label: 'Por pagar', icon: CalendarClock },
      { to: '/proveedores', label: 'Proveedores', icon: Building2 },
    ],
  },
  {
    label: 'Finanzas',
    items: [
      { to: '/reportes', label: 'Reportes', icon: BarChart3 },
      {
        to: '/contabilidad',
        label: 'Contabilidad',
        icon: BookOpen,
        roles: ['OWNER', 'ADMIN', 'ACCOUNTANT'],
      },
      { to: '/propuestas', label: 'Propuestas', icon: Sparkles },
    ],
  },
]

const QUICK_ACTIONS = [
  { to: '/ingresos?nuevo=1', label: 'Ingreso' },
  { to: '/gastos?nuevo=1', label: 'Gasto' },
  { to: '/por-cobrar?nueva=1', label: 'Cuenta por cobrar' },
  { to: '/por-pagar?nueva=1', label: 'Cuenta por pagar' },
  { to: '/movimientos?transferir=1', label: 'Traspaso' },
  { to: '/clientes?nuevo=1', label: 'Cliente' },
  { to: '/proveedores?nuevo=1', label: 'Proveedor' },
  { to: '/cuentas?nueva=1', label: 'Cuenta de dinero' },
]

export function AppLayout() {
  const [navOpen, setNavOpen] = useState(false)

  const { data: pendingProposals } = useQuery({
    queryKey: ['proposals-count'],
    queryFn: async () => (await api.get<{ count: number }>('/proposals/pending-count')).data.count,
    refetchInterval: 60_000,
  })

  // MVP: el rol se infiere del registro (OWNER). Cuando haya multiusuario real,
  // vendrá de /api/me; la autoridad siempre es el backend.
  const role = 'OWNER'

  return (
    <div className="flex h-full">
      {navOpen ? (
        <div
          className="fixed inset-0 z-40 bg-ink/50 lg:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden
        />
      ) : null}

      {/* La barra lateral hace una sola cosa: navegar. Identidad, acciones y
          usuario viven en el encabezado. */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col bg-rail text-rail-ink transition-transform lg:static lg:translate-x-0 ${
          navOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-2.5 px-5 pb-5 pt-5">
          <ArcaMark />
          <div className="min-w-0">
            <div className="font-display text-lg font-bold leading-none tracking-tight">ARCA</div>
            <div className="figures mt-1 text-[9px] uppercase tracking-[0.2em] text-rail-muted">
              Financial OS
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 pb-4">
          {NAV_SECTIONS.map((section, index) => (
            <div key={index} className="mb-4">
              {section.label ? (
                <div className="px-2.5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-rail-muted">
                  {section.label}
                </div>
              ) : null}
              {section.items
                .filter((item) => !item.roles || item.roles.includes(role))
                .map((item) => {
                  const Icon = item.icon
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      onClick={() => setNavOpen(false)}
                      className={({ isActive }) =>
                        `mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition-colors ${
                          isActive
                            ? 'bg-white/10 font-medium text-white'
                            : 'text-rail-ink/75 hover:bg-white/5 hover:text-white'
                        }`
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <Icon
                            className={`h-4 w-4 shrink-0 ${isActive ? 'text-accent' : 'text-rail-muted'}`}
                          />
                          <span className="flex-1 truncate">{item.label}</span>
                          {item.to === '/propuestas' && (pendingProposals ?? 0) > 0 ? (
                            <span className="figures rounded-full bg-accent px-1.5 py-0.5 text-[10px] font-bold text-on-accent">
                              {pendingProposals}
                            </span>
                          ) : null}
                        </>
                      )}
                    </NavLink>
                  )
                })}
            </div>
          ))}
        </nav>

      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <AppHeader quickActions={QUICK_ACTIONS} onOpenNav={() => setNavOpen(true)} />
        <main className="flex-1">
          <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
            <Outlet />
          </div>
        </main>
        <AppFooter />
      </div>
    </div>
  )
}
