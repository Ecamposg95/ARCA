import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, LogOut, Menu, Plus, Settings, Search } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { CompanySwitcher } from '@/components/layout/CompanySwitcher'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { useDismiss } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'

const MENU_ITEM =
  'flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-2'

export function AppHeader({
  quickActions,
  onOpenNav,
  onOpenPalette,
}: {
  quickActions: { to: string; label: string }[]
  onOpenNav: () => void
  onOpenPalette: () => void
}) {
  const navigate = useNavigate()
  const { user, logout } = useAuthStore()
  const [quickOpen, setQuickOpen] = useState(false)
  const [userOpen, setUserOpen] = useState(false)

  const quickRef = useDismiss(() => setQuickOpen(false))
  const userRef = useDismiss(() => setUserOpen(false))

  const initials = (user?.name ?? '?')
    .split(' ')
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('')

  return (
    <header className="z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4 lg:px-6">
      <button
        type="button"
        onClick={onOpenNav}
        aria-label="Abrir navegación"
        className="-ml-1 rounded-lg p-2 text-muted transition-colors hover:bg-surface-2 hover:text-ink lg:hidden"
      >
        <Menu className="h-5 w-5" />
      </button>

      <CompanySwitcher />

      {/* La paleta existe aunque nadie sepa el atajo: el botón la descubre. */}
      <button
        type="button"
        onClick={onOpenPalette}
        className="hidden items-center gap-2 rounded-lg border border-border bg-surface-2/60 px-3 py-1.5 text-xs text-muted transition-colors hover:text-ink sm:flex"
      >
        <Search className="h-3.5 w-3.5" />
        Buscar o crear
        <kbd className="figures rounded border border-border bg-surface px-1.5 text-[10px]">
          Ctrl K
        </kbd>
      </button>

      <div className="relative" ref={quickRef}>
        <Button className="shrink-0 !px-3 !py-1.5" onClick={() => setQuickOpen((open) => !open)}>
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">Nuevo</span>
        </Button>
        {quickOpen ? (
          <div className="absolute right-0 top-11 w-56 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-float">
            {quickActions.map((action) => (
              <button
                key={action.to}
                type="button"
                className={MENU_ITEM}
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

      <div className="relative" ref={userRef}>
        <button
          type="button"
          onClick={() => setUserOpen((open) => !open)}
          className="flex items-center gap-2 rounded-lg py-1 pl-1 pr-1.5 transition-colors hover:bg-surface-2"
          aria-label="Menú de usuario"
        >
          <span className="figures flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-[11px] font-bold text-accent">
            {initials}
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-muted" />
        </button>
        {userOpen ? (
          <div className="absolute right-0 top-11 w-56 overflow-hidden rounded-xl border border-border bg-surface py-1 shadow-float">
            <div className="border-b border-border px-3.5 pb-2 pt-1.5">
              <div className="truncate text-sm font-medium">{user?.name}</div>
              <div className="truncate text-xs text-muted">{user?.email}</div>
            </div>
            <div className="flex items-center justify-between px-3.5 py-2">
              <span className="text-sm text-muted">Tema</span>
              <ThemeToggle />
            </div>
            <button
              type="button"
              className={MENU_ITEM}
              onClick={() => {
                setUserOpen(false)
                navigate('/configuracion')
              }}
            >
              <Settings className="h-4 w-4 text-muted" />
              Configuración
            </button>
            <button
              type="button"
              className={MENU_ITEM}
              onClick={() => {
                logout()
                navigate('/login')
              }}
            >
              <LogOut className="h-4 w-4 text-muted" />
              Cerrar sesión
            </button>
          </div>
        ) : null}
      </div>
    </header>
  )
}
