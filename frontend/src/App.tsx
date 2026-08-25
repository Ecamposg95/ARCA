import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AppLayout } from '@/components/layout/AppLayout'
import { AccountingPage } from '@/features/accounting/AccountingPage'
import { AccountsPage } from '@/features/accounts/AccountsPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { ContactsPage, CUSTOMERS_CONFIG, VENDORS_CONFIG } from '@/features/contacts/ContactsPage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { DebtsPage, PAYABLES_CONFIG, RECEIVABLES_CONFIG } from '@/features/debts/DebtsPage'
import { EXPENSE_CONFIG, INCOME_CONFIG, OperationsPage } from '@/features/operations/OperationsPage'
import { ReportsPage } from '@/features/reports/ReportsPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { TransactionsPage } from '@/features/transactions/TransactionsPage'
import { useAuthStore } from '@/stores/authStore'

function PrivateRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace />
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/registro" element={<RegisterPage />} />
        <Route element={<PrivateRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/movimientos" element={<TransactionsPage />} />
            <Route path="/cuentas" element={<AccountsPage />} />
            <Route path="/ingresos" element={<OperationsPage config={INCOME_CONFIG} />} />
            <Route path="/gastos" element={<OperationsPage config={EXPENSE_CONFIG} />} />
            <Route path="/por-cobrar" element={<DebtsPage config={RECEIVABLES_CONFIG} />} />
            <Route path="/por-pagar" element={<DebtsPage config={PAYABLES_CONFIG} />} />
            <Route path="/clientes" element={<ContactsPage config={CUSTOMERS_CONFIG} />} />
            <Route path="/proveedores" element={<ContactsPage config={VENDORS_CONFIG} />} />
            <Route path="/contabilidad" element={<AccountingPage />} />
            <Route path="/reportes" element={<ReportsPage />} />
            <Route path="/configuracion" element={<SettingsPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
