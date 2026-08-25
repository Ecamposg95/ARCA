import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { ArcaMark } from '@/components/ui/ArcaMark'
import { Button } from '@/components/ui/Button'

const NAV_SECTIONS: { label: string | null; items: { to: string; label: string; roles?: string[] }[] }[] = [
  { label: null, items: [{ to: '/', label: 'Inicio' }] },
  {
    label: 'Dinero',
    items: [
      { to: '/movimientos', label: 'Movimientos' },
      { to: '/cuentas', label: 'Cuentas' },
    ],
  },
  {
    label: 'Ventas',
    items: [
      { to: '/ingresos', label: 'Ingresos' },
      { to: '/por-cobrar', label: 'Por cobrar' },
      { to: '/clientes', label: 'Clientes' },
    ],
  },
  {
    label: 'Gastos',
    items: [
      { to: '/gastos', label: 'Gastos' },
      { to: '/por-pagar', label: 'Por pagar' },
      { to: '/proveedores', label: 'Proveedores' },
    ],
  },
  {
    label: 'Finanzas',
    items: [
      { to: '/reportes', label: 'Reportes' },
      { to: '/contabilidad', label: 'Contabilidad', roles: ['OWNER', 'ADMIN', 'ACCOUNTANT'] },
      { to: '/propuestas', label: 'Propuestas' },
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
  const { user, organization, logout } = useAuthStore()
  const navigate = useNavigate()
  const [quickOpen, setQuickOpen] = useState(false)
  const [navOpen, setNavOpen] = useState(false)

  const { data: pendingProposals } = useQuery({
    queryKey: ['proposals-count'],
    queryFn: async () => (await api.get<{ count: number }>('/proposals/pending-count')).data.count,
    refetchInterval: 60_000,
  })

  // MVP: el rol se infiere del registro (OWNER). Cuando haya multiusuario real,
  // vendrá de /api/me; la autoridad siempre es el backend.
  const role = 'OWNER'

  function go(to: string) {
    setQuickOpen(false)
    setNavOpen(false)
    navigate(to)
  }

  return (
    <div className="flex h-full">
      {/* Barra superior sólo en móvil: abre el cajón de navegación. */}
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center gap-3 border-b border-white/10 bg-rail px-4 text-rail-ink lg:hidden">
        <button
          type="button"
          onClick={() => setNavOpen(true)}
          aria-label="Abrir navegación"
          className="rounded-lg p-2 hover:bg-white/10"
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M3 5.5h14M3 10h14M3 14.5h14" strokeLinecap="round" />
          </svg>
        </button>
        {/* min-w-0: sin esto el truncate no encoge y el botón se sale de la pantalla. */}
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{organization?.name}</span>
        <Button
          className="shrink-0 !px-3 !py-1.5 text-xs"
          onClick={() => setQuickOpen((value) => !value)}
        >
          + Nuevo
        </Button>
        {quickOpen ? (
          <div className="absolute right-4 top-12 z-40 w-56 overflow-hidden rounded-xl bg-surface py-1 shadow-float">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.to}
                type="button"
                className="block w-full px-4 py-2 text-left text-sm text-ink hover:bg-surface-2"
                onClick={() => go(action.to)}
              >
                {action.label}
              </button>
            ))}
          </div>
        ) : null}
      </header>

      {navOpen ? (
        <div
          className="fixed inset-0 z-30 bg-ink/50 lg:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-60 shrink-0 flex-col bg-rail text-rail-ink transition-transform lg:static lg:translate-x-0 ${
          navOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-2.5 px-5 pb-6 pt-6">
          <ArcaMark />
          <div className="min-w-0">
            <div className="font-display text-lg font-bold leading-none tracking-tight">ARCA</div>
            <div className="mt-0.5 truncate text-xs text-rail-muted">{organization?.name}</div>
          </div>
        </div>

        <div className="hidden px-4 pb-4 lg:block">
          <div className="relative">
            <Button className="w-full" onClick={() => setQuickOpen((value) => !value)}>
              + Nuevo
            </Button>
            {quickOpen ? (
              <div className="absolute left-0 right-0 z-40 mt-1.5 overflow-hidden rounded-xl bg-surface py-1 shadow-float">
                {QUICK_ACTIONS.map((action) => (
                  <button
                    key={action.to}
                    type="button"
                    className="block w-full px-4 py-2 text-left text-sm text-ink hover:bg-surface-2"
                    onClick={() => go(action.to)}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3">
          {NAV_SECTIONS.map((section, index) => (
            <div key={index} className="mb-4">
              {section.label ? (
                <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-widest text-rail-muted">
                  {section.label}
                </div>
              ) : null}
              {section.items
                .filter((item) => !item.roles || item.roles.includes(role))
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    onClick={() => setNavOpen(false)}
                    className={({ isActive }) =>
                      `block rounded-lg px-2.5 py-1.5 text-sm transition-colors ${
                        isActive
                          ? 'bg-white/10 font-medium text-white'
                          : 'text-rail-ink/80 hover:bg-white/5 hover:text-white'
                      }`
                    }
                  >
                    <span className="flex items-center justify-between">
                      {item.label}
                      {item.to === '/propuestas' && (pendingProposals ?? 0) > 0 ? (
                        <span className="figures rounded-full bg-accent px-1.5 py-0.5 text-[10px] font-bold text-white">
                          {pendingProposals}
                        </span>
                      ) : null}
                    </span>
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>

        <div className="border-t border-white/10 px-5 py-4">
          <div className="truncate text-sm">{user?.name}</div>
          <div className="mt-1 flex items-center justify-between">
            <NavLink
              to="/configuracion"
              onClick={() => setNavOpen(false)}
              className="text-xs text-rail-muted hover:text-white"
            >
              Configuración
            </NavLink>
            <button
              type="button"
              className="text-xs text-rail-muted hover:text-white"
              onClick={() => {
                logout()
                navigate('/login')
              }}
            >
              Salir
            </button>
          </div>
        </div>
      </aside>

      <main
        className="min-w-0 flex-1 overflow-y-auto pt-14 lg:pt-0"
        onClick={() => quickOpen && setQuickOpen(false)}
      >
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8 lg:px-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
