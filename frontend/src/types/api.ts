export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface User {
  id: string
  email: string
  name: string
  status: string
}

export interface Organization {
  id: string
  name: string
  legal_name: string | null
  tax_id: string | null
  currency: string
  country: string
  timezone: string
  business_type: string | null
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user: User
  organization: Organization | null
}

export interface FinancialAccount {
  id: string
  name: string
  type: 'CASH' | 'BANK' | 'CREDIT_CARD' | 'OTHER'
  currency: string
  opening_balance: string
  current_balance: string
  institution: string | null
  last_four: string | null
  active: boolean
  created_at: string
}

export interface Category {
  id: string
  name: string
  kind: 'INCOME' | 'EXPENSE'
  account_code: string
  active: boolean
}

export interface Contact {
  id: string
  name: string
  legal_name: string | null
  tax_id: string | null
  email: string | null
  phone: string | null
  notes: string | null
  status: string
  created_at: string
}

export type OperationStatus = 'PENDING' | 'PAID' | 'CANCELLED'

export interface Income {
  id: string
  date: string
  customer_id: string | null
  description: string
  amount: string
  category_id: string
  financial_account_id: string | null
  status: OperationStatus
  notes: string | null
  paid_at: string | null
  created_at: string
}

export interface Expense {
  id: string
  date: string
  vendor_id: string | null
  description: string
  amount: string
  category_id: string
  financial_account_id: string | null
  payment_method: string | null
  reference: string | null
  status: OperationStatus
  notes: string | null
  paid_at: string | null
  created_at: string
}

export interface AgentKey {
  id: string
  name: string
  key_prefix: string
  scopes: string
  active: boolean
  last_used_at: string | null
  created_at: string
  token?: string // solo presente al crear
}

export interface Proposal {
  id: string
  kind: 'INCOME' | 'EXPENSE' | 'RECEIVABLE' | 'PAYABLE'
  payload: Record<string, unknown>
  summary: string
  evidence: string | null
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED'
  rejection_reason: string | null
  result_id: string | null
  created_at: string
  agent_name: string | null
}

export type DebtDisplayStatus = 'OPEN' | 'PARTIAL' | 'PAID' | 'CANCELLED' | 'OVERDUE'

export interface Debt {
  id: string
  customer_id?: string
  vendor_id?: string
  description: string
  amount: string
  amount_paid: string
  balance: string
  date: string
  due_date: string
  category_id: string
  status: string
  display_status: DebtDisplayStatus
  is_overdue: boolean
  notes: string | null
  created_at: string
}

export interface Transaction {
  id: string
  financial_account_id: string
  transaction_type: string
  amount: string
  currency: string
  date: string
  description: string
  reference: string | null
  status: string
  source_type: string | null
  created_at: string
}

export interface DashboardSummary {
  cash: number
  monthly_revenue: number
  monthly_expenses: number
  monthly_profit: number
  receivables: number
  overdue_receivables: number
  payables: number
  cash_flow: { month: string; inflows: number; outflows: number }[]
  revenue_vs_expenses: { month: string; revenue: number; expenses: number }[]
  expense_categories: { category: string; amount: number }[]
}

export interface ReportLine {
  code: string
  name: string
  type: string
  amount: number
}

export interface ProfitLoss {
  start: string
  end: string
  revenue: ReportLine[]
  expenses: ReportLine[]
  total_revenue: number
  total_expenses: number
  net_profit: number
}

export interface BalanceSheet {
  as_of: string
  assets: ReportLine[]
  liabilities: ReportLine[]
  equity: ReportLine[]
  total_assets: number
  total_liabilities: number
  total_equity: number
  balanced: boolean
}

export interface CashFlow {
  start: string
  end: string
  opening_cash: number
  inflows: number
  outflows: number
  closing_cash: number
}

export interface JournalLine {
  id: string
  account_id: string
  debit: string
  credit: string
  description: string | null
}

export interface JournalEntry {
  id: string
  folio: string
  kind: 'INGRESO' | 'EGRESO' | 'DIARIO'
  date: string
  description: string
  reference: string | null
  source_type: string | null
  source_id: string | null
  status: string
  lines: JournalLine[]
}

export interface LedgerAccount {
  id: string
  code: string
  name: string
  type: string
  parent_id: string | null
  active: boolean
}

export interface TrialBalanceRow {
  code: string
  name: string
  type: string
  debit: number
  credit: number
  balance: number
}
