import { Suspense, lazy } from 'react'
import type { ComponentType } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { useAuthStore } from '@/stores/authStore'

/* Cada ruta carga su módulo cuando se visita: el bundle inicial deja de cargar
 * recharts y las quince pantallas para pintar un login. Las páginas exportan
 * componentes nombrados y sus configs desde el mismo módulo, así que el
 * selector de config vive DENTRO del import diferido — importar la config
 * arriba arrastraría el módulo completo al bundle inicial y anularía todo. */
function lazyRoute<M>(
  loader: () => Promise<M>,
  pick: (module: M) => ComponentType,
) {
  return lazy(() => loader().then((module) => ({ default: pick(module) })))
}

const LoginPage = lazyRoute(
  () => import('@/features/auth/LoginPage'),
  (m) => m.LoginPage,
)
const RegisterPage = lazyRoute(
  () => import('@/features/auth/RegisterPage'),
  (m) => m.RegisterPage,
)
const DashboardPage = lazyRoute(
  () => import('@/features/dashboard/DashboardPage'),
  (m) => m.DashboardPage,
)
const TransactionsPage = lazyRoute(
  () => import('@/features/transactions/TransactionsPage'),
  (m) => m.TransactionsPage,
)
const AccountsPage = lazyRoute(
  () => import('@/features/accounts/AccountsPage'),
  (m) => m.AccountsPage,
)
const AssetsPage = lazyRoute(
  () => import('@/features/assets/AssetsPage'),
  (m) => m.AssetsPage,
)
const ProjectsPage = lazyRoute(
  () => import('@/features/projects/ProjectsPage'),
  (m) => m.ProjectsPage,
)
const IncomePage = lazyRoute(
  () => import('@/features/operations/OperationsPage'),
  (m) => () => <m.OperationsPage config={m.INCOME_CONFIG} />,
)
const ExpensesPage = lazyRoute(
  () => import('@/features/operations/OperationsPage'),
  (m) => () => <m.OperationsPage config={m.EXPENSE_CONFIG} />,
)
const ReceivablesPage = lazyRoute(
  () => import('@/features/debts/DebtsPage'),
  (m) => () => <m.DebtsPage config={m.RECEIVABLES_CONFIG} />,
)
const PayablesPage = lazyRoute(
  () => import('@/features/debts/DebtsPage'),
  (m) => () => <m.DebtsPage config={m.PAYABLES_CONFIG} />,
)
const CustomersPage = lazyRoute(
  () => import('@/features/contacts/ContactsPage'),
  (m) => () => <m.ContactsPage config={m.CUSTOMERS_CONFIG} />,
)
const VendorsPage = lazyRoute(
  () => import('@/features/contacts/ContactsPage'),
  (m) => () => <m.ContactsPage config={m.VENDORS_CONFIG} />,
)
const AccountingPage = lazyRoute(
  () => import('@/features/accounting/AccountingPage'),
  (m) => m.AccountingPage,
)
const ProposalsPage = lazyRoute(
  () => import('@/features/proposals/ProposalsPage'),
  (m) => m.ProposalsPage,
)
const ReportsPage = lazyRoute(
  () => import('@/features/reports/ReportsPage'),
  (m) => m.ReportsPage,
)
const SettingsPage = lazyRoute(
  () => import('@/features/settings/SettingsPage'),
  (m) => m.SettingsPage,
)

/** Mientras llega el chunk de la ruta: el mismo esqueleto que usan las páginas
 *  al cargar datos, para que el cambio de ruta no parpadee distinto. */
function RouteFallback() {
  return (
    <div className="space-y-4 p-1">
      <div className="h-8 w-56 animate-pulse rounded-lg bg-surface-2" />
      <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
    </div>
  )
}

function PrivateRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
}

/** El Suspense va DENTRO del layout: si envolviera todo, cada cambio de ruta
 *  desmontaría el sidebar y el encabezado mientras llega el chunk. Así el cromo
 *  queda fijo y sólo el contenido muestra el esqueleto. */
function SuspenseOutlet() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Outlet />
    </Suspense>
  )
}

export function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/registro" element={<RegisterPage />} />
          <Route element={<PrivateRoute />}>
            <Route element={<AppLayout />}>
              <Route element={<SuspenseOutlet />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/movimientos" element={<TransactionsPage />} />
              <Route path="/cuentas" element={<AccountsPage />} />
              <Route path="/patrimonio" element={<AssetsPage />} />
              <Route path="/proyectos" element={<ProjectsPage />} />
              <Route path="/ingresos" element={<IncomePage />} />
              <Route path="/gastos" element={<ExpensesPage />} />
              <Route path="/por-cobrar" element={<ReceivablesPage />} />
              <Route path="/por-pagar" element={<PayablesPage />} />
              <Route path="/clientes" element={<CustomersPage />} />
              <Route path="/proveedores" element={<VendorsPage />} />
              <Route path="/contabilidad" element={<AccountingPage />} />
              <Route path="/propuestas" element={<ProposalsPage />} />
              <Route path="/reportes" element={<ReportsPage />} />
              <Route path="/configuracion" element={<SettingsPage />} />
              </Route>
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
