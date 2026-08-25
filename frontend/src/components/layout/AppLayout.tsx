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
      <aside className="flex w-60 shrink-0 flex-col bg-rail text-rail-ink">
        <div className="flex items-center gap-2.5 px-5 pb-6 pt-6">
          <ArcaMark />
          <div>
            <div className="font-display text-lg font-bold leading-none tracking-tight">ARCA</div>
            <div className="mt-0.5 truncate text-xs text-rail-muted">{organization?.name}</div>
          </div>
        </div>

        <div className="px-4 pb-4">
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
                    onClick={() => {
                      setQuickOpen(false)
                      navigate(action.to)
                    }}
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
            <NavLink to="/configuracion" className="text-xs text-rail-muted hover:text-white">
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

      <main className="min-w-0 flex-1 overflow-y-auto" onClick={() => quickOpen && setQuickOpen(false)}>
        <div className="mx-auto max-w-6xl px-6 py-8 lg:px-10">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
