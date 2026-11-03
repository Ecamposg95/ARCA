export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
  /** Suma de TODO el filtro (no sólo de la página). Sólo en listas de dinero. */
  total_amount?: string | number
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
  default_tax_rate: string
  ai_budget_usd: string | null
  ai_enabled: boolean
  /** Si la empresa definió unidades o contribuyentes (sólo en /organizations/current). */
  has_business_units?: boolean
  has_fiscal_entities?: boolean
}

/** Sucursal, toma de muestra, unidad móvil o canal: una etiqueta del libro, no una cuenta. */
export interface BusinessUnit {
  id: string
  name: string
  code: string
  kind: 'MATRIZ' | 'TOMA_MUESTRA' | 'UNIDAD_MOVIL' | 'CANAL' | 'OTRA'
  active: boolean
  opened_on: string | null
  aliases: string[]
  sort_order: number
  accounts_count: number
  created_at: string
}

/** Contribuyente bajo el que se declara una operación. */
export interface FiscalEntity {
  id: string
  name: string
  tax_id: string | null
  regime: string | null
  active: boolean
  sort_order: number
  created_at: string
}

/** Las dos dimensiones opcionales que lleva cada operación y su póliza. */
export interface Dimensioned {
  business_unit_id: string | null
  business_unit_name: string | null
  fiscal_entity_id: string | null
  fiscal_entity_name: string | null
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
  type: 'CASH' | 'BANK' | 'CREDIT_CARD' | 'PROCESSOR' | 'OTHER'
  currency: string
  opening_balance: string
  current_balance: string
  institution: string | null
  last_four: string | null
  credit_limit: string | null
  is_liability: boolean
  /** false en un procesador de pagos: el cobro es tuyo pero aún no llega al banco. */
  available: boolean
  available_credit: string | null
  active: boolean
  /** A qué unidad pertenece la caja; las operaciones pagadas con ella la heredan. */
  business_unit_id: string | null
  business_unit_name: string | null
  /** Sólo procesadores: comisión pactada (0.0350 = 3.5 %), días en que deposita y banco destino. */
  fee_rate: string | null
  settlement_days: number | null
  settlement_account_id: string | null
  created_at: string
}

/** Liquidación de un procesador: el neto pasa al banco y la comisión es gasto. */
export interface Settlement {
  id: string
  processor_account_id: string
  bank_account_id: string
  date: string
  gross_amount: string
  fee_amount: string
  net_amount: string
  reference: string | null
  notes: string | null
  status: 'ACTIVE' | 'CANCELLED'
  transfer_group_id: string
  expense_id: string | null
  created_by: string | null
  cancelled_at: string | null
  created_at: string
}

export type CashCutStatus = 'OPEN' | 'COUNTED' | 'DELIVERED' | 'CANCELLED'

/** Corte de caja de un día: esperado vs contado, diferencia y entrega. */
export interface CashCut {
  id: string
  financial_account_id: string
  account_name: string | null
  business_unit_id: string | null
  business_unit_name: string | null
  date: string
  opening_balance: string
  inflows: string
  outflows: string
  expected_closing: string
  counted_amount: string | null
  difference: string | null
  explanation: string | null
  status: CashCutStatus
  delivered_amount: string | null
  delivered_to_account_id: string | null
  delivered_to_account_name: string | null
  delivered_by: string | null
  delivered_by_name: string | null
  delivered_at: string | null
  received_by: string | null
  received_by_name: string | null
  received_at: string | null
  transfer_group_id: string | null
  adjustment_transaction_id: string | null
  closed_at: string | null
  cancelled_at: string | null
  created_at: string
}

export interface TodayCashRow {
  account_id: string
  account_name: string
  business_unit_id: string | null
  business_unit_name: string | null
  current_balance: string
  cut: CashCut | null
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

export interface Income extends Dimensioned {
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

export interface Expense extends Dimensioned {
  id: string
  date: string
  vendor_id: string | null
  description: string
  amount: string
  category_id: string
  financial_account_id: string | null
  payment_method: string | null
  reference: string | null
  retention_isr: string
  retention_iva: string
  /** Aviso fiscal calculado en el backend (LISR 27-III). */
  deductibility_warning: string | null
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

export type ProposalKind =
  | 'INCOME'
  | 'EXPENSE'
  | 'RECEIVABLE'
  | 'PAYABLE'
  | 'EXPENSE_PAYMENT'
  | 'PAYABLE_PAYMENT'
  | 'TRANSFER'

/** De dónde salió una propuesta: lo capturó alguien y espera autorización,
 *  lo propuso un agente, el asistente o ONE Finance (recurrentes). */
export type ProposalSource = 'approval' | 'agent' | 'assistant' | 'system'

export interface Proposal {
  id: string
  kind: ProposalKind
  payload: Record<string, unknown>
  summary: string
  evidence: string | null
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED'
  rejection_reason: string | null
  result_id: string | null
  created_at: string
  agent_name: string | null
  source: ProposalSource | null
  requested_by_name: string | null
}

/** Cuerpo del 202: la operación no se registró, espera a quien autoriza. */
export interface PendingApproval {
  pending_approval: true
  proposal_id: string
  detail: string
  authorizers: string[]
}

/** Autorización por monto de la empresa. Vacío = sin autorización / sin límite. */
export interface ApprovalSettings {
  approval_threshold: string | null
  member_capture_limit: string | null
}

export type DebtDisplayStatus = 'OPEN' | 'PARTIAL' | 'PAID' | 'CANCELLED' | 'OVERDUE'

export interface Debt extends Dimensioned {
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

export interface Transaction extends Dimensioned {
  id: string
  financial_account_id: string
  transaction_type: string
  amount: string
  currency: string
  date: string
  description: string
  reference: string | null
  status: string
  payment_method: string | null
  source_type: string | null
  running_balance: string | null
  created_at: string
}

export interface DashboardSummary {
  cash: number
  /** Por recibir de procesadores de pago: cobrado con tarjeta, aún no depositado. */
  in_transit_total: number
  card_debt: number
  monthly_revenue: number
  monthly_expenses: number
  monthly_profit: number
  previous_revenue: number
  previous_expenses: number
  previous_profit: number
  receivables: number
  overdue_receivables: number
  payables: number
  cash_flow: { month: string; inflows: number; outflows: number }[]
  revenue_vs_expenses: { month: string; revenue: number; expenses: number }[]
  expense_categories: { category: string; amount: number }[]
}

export interface FlowPoint {
  bucket: string
  start: string
  inflows: number
  outflows: number
  net: number
  top_expense_categories: { category: string; amount: number }[]
}

export interface CashFlowSeries {
  granularity: 'month' | 'week'
  points: FlowPoint[]
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

export interface ProjectRow {
  id: string
  name: string
  code: string | null
  customer_id: string | null
  description: string | null
  budget: string | null
  start_date: string | null
  end_date: string | null
  status: string
  created_at: string
  revenue: string
  cost: string
  margin: string
  margin_pct: number
  pending_revenue: string
  budget_used_pct: number | null
}

export interface ProjectsResponse {
  items: ProjectRow[]
  total: number
  limit: number
  offset: number
  unassigned: { revenue: string; cost: string; margin: string; margin_pct: number }
}

export interface FixedAsset {
  id: string
  name: string
  category: string
  acquisition_date: string
  cost: string
  tax_amount: string
  salvage_value: string
  useful_life_months: number
  accumulated_depreciation: string
  financial_account_id: string | null
  vendor_id: string | null
  status: string
  disposed_at: string | null
  notes: string | null
  created_at: string
  book_value: string
  monthly_depreciation: string
  months_remaining: number
}

export interface Loan {
  id: string
  lender: string
  description: string
  principal: string
  outstanding: string
  annual_rate: string
  term_months: number
  start_date: string
  payment_day: number
  financial_account_id: string | null
  status: string
  notes: string | null
  created_at: string
  monthly_payment: string
  paid_principal: string
}

export interface LoanScheduleRow {
  number: number
  due_date: string
  payment: string
  principal: string
  interest: string
  balance: string
}

export interface LoanSchedule {
  loan_id: string
  monthly_payment: string
  rows: LoanScheduleRow[]
}

export interface AgingContact {
  contact_id: string
  name: string
  total: number
  oldest_days: number
  /** Un campo por tramo ("0-30", "31-60", "61-90", "+90"). */
  [bucket: string]: number | string
}

export interface AgingReport {
  as_of: string
  kind: 'receivable' | 'payable'
  buckets: string[]
  contacts: AgingContact[]
  totals: Record<string, number>
  total: number
  overdue: number
  average_days: number
  previous_average_days: number | null
}

export interface NetWorthPoint {
  month: string
  assets: number
  liabilities: number
  net_worth: number
}

export interface NetWorth {
  as_of: string
  assets: ReportLine[]
  liabilities: ReportLine[]
  total_assets: number
  total_liabilities: number
  net_worth: number
  change_vs_previous_month: number
  series: NetWorthPoint[]
}

export interface JournalLine {
  id: string
  account_id: string
  debit: string
  credit: string
  description: string | null
}

export interface JournalEntry extends Dimensioned {
  id: string
  folio: string
  kind: 'INGRESO' | 'EGRESO' | 'DIARIO'
  date: string
  description: string
  reference: string | null
  source_type: string | null
  source_id: string | null
  status: string
  /** Ya tiene póliza espejo. */
  reversed: boolean
  /** Id de la póliza que este reverso deshace, o null. */
  reversal_of: string | null
  /** La póliza espejo que la deshizo, o null. */
  reversed_by: { id: string; folio: string; date: string } | null
  /** Folio de la póliza que este reverso deshace, o null. */
  reversal_of_folio: string | null
  lines: JournalLine[]
}

export interface LedgerAccount {
  id: string
  code: string
  name: string
  type: string
  parent_id: string | null
  active: boolean
  /** Número de la misma cuenta en el CONTPAQi del contador, o null. */
  contpaqi_code: string | null
  /** Código agrupador del SAT (Anexo 24), o null. */
  sat_code: string | null
  /** La sembró ONE Finance al crear la empresa; las reglas la usan y no se desactiva. */
  system: boolean
  /** Tiene al menos una línea en el ledger; una cuenta así no se desactiva. */
  has_movements: boolean
  /** Acepta pólizas manuales (de detalle, activa y sin saldo espejo de un módulo); lo decide el backend. */
  manual_allowed: boolean
}

/** GET /accounting/opening-balance: la apertura viva y contra qué puede cuadrar. */
export interface OpeningBalance {
  /** La póliza de apertura vigente (sin reverso), o null si no hay. */
  entry: JournalEntry | null
  /** Cuentas de cuadre permitidas, en orden: ["3200", "3100"]. */
  balancing_codes: string[]
}

/** Un renglón de GET /periods/years. Montos como texto. */
export interface FiscalYear {
  year: number
  entries: number
  revenue: string
  expenses: string
  result: string
  closed: boolean
  /** Terminó, sigue abierto y es el siguiente en orden. */
  can_close: boolean
  /** Año anterior con resultados que sigue abierto y debe cerrarse primero, o null. */
  blocked_by: number | null
  /** Póliza de cierre vigente (sólo si está cerrado y tuvo resultados), o null. */
  closing_entry_id: string | null
  closing_folio: string | null
  /** Última reapertura, si el año está abierto después de haberse cerrado. */
  reopened_at: string | null
}

export interface TrialBalanceRow {
  code: string
  name: string
  type: string
  debit: number
  credit: number
  balance: number
}

export interface VatReport {
  start: string
  end: string
  vat_charged: number
  vat_creditable: number
  difference: number
  to_pay: number
  in_favor: number
  vat_pending_collection: number
  vat_pending_payment: number
}

export interface CashProjection {
  start: string
  end: string
  opening_cash: number
  expected_inflows: number
  expected_outflows: number
  projected_cash: number
  shortfall_date: string | null
  points: { date: string; balance: number; change: number; description?: string }[]
}

export interface Membership {
  organization_id: string
  role: string
  /** Facultad efectiva de autorizar (el dueño siempre la tiene). */
  can_authorize: boolean
}

export interface MeResponse {
  user: User
  memberships: Membership[]
  organizations: Organization[]
}

export type PortfolioStatus = 'red' | 'amber' | 'green'

/** Una fila de la cartera: una empresa del usuario y lo que tiene pendiente. */
export interface PortfolioItem {
  organization_id: string
  name: string
  tax_id: string | null
  business_type: string | null
  role: string
  cash: string
  receivable: string
  payable_overdue: string
  /** "AAAA-MM" del último mes cerrado, o null si nunca ha cerrado uno. */
  last_closed_period: string | null
  previous_month_closed: boolean
  pending_proposals: number
  status: PortfolioStatus
  reasons: string[]
}

export interface SatCode {
  code: string
  name: string
}

// --- Asistente ONE Finance sobre Claude (spec 2026-11-02) ---

export interface AssistantStatus {
  available: boolean
  reason: 'sin_llave' | 'deshabilitado' | 'sin_presupuesto' | null
  model: string
  model_name: string
  budget_usd: string
  spent_usd: string
  remaining_usd: string
}

export interface AssistantConversationLite {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface AssistantStep {
  name: string
  ok: boolean
  summary: string | null
}

export interface AssistantAction {
  id: string
  tool_name: string
  summary: string
  args: Record<string, unknown>
  proposal_id: string | null
  proposal_kind: 'INCOME' | 'EXPENSE' | 'RECEIVABLE' | 'PAYABLE' | null
  status: 'PENDING' | 'APPROVED' | 'REJECTED'
  resolved_at: string | null
  created_at: string
}

export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  text: string | null
  steps: AssistantStep[]
  actions: AssistantAction[]
  stop_reason: string | null
  input_tokens: number
  output_tokens: number
  cost_usd: string
  created_at: string
}

export interface AssistantConversation {
  id: string
  title: string | null
  busy: boolean
  messages: AssistantMessage[]
  created_at: string
  updated_at: string
}

export interface AssistantUsageRow {
  key: string
  label: string
  calls: number
  cost_usd: string
}

export interface AssistantUsage {
  month: string
  budget_usd: string
  total_usd: string
  calls: number
  by_user: AssistantUsageRow[]
  by_day: AssistantUsageRow[]
}

// --- Importación -------------------------------------------------------------

export type ImportKind = 'TORONJA' | 'INCOMES' | 'EXPENSES' | 'CASH'
export type ImportBatchStatus = 'PREVIEW' | 'CONFIRMED' | 'DISCARDED'
export type ImportRowStatus = 'OK' | 'ERROR' | 'DUPLICATE' | 'SKIPPED' | 'CREATED'

export interface ImportSummary {
  rows: number
  ok: number
  errors: number
  duplicates: number
  skipped: number
  created: number
  /** Operaciones que se crearán (Toronja agrupa varios tickets en una). */
  operations: number
  /** Rango de fechas de lo que entra (AAAA-MM-DD), para enlazar las listas filtradas. */
  from: string | null
  to: string | null
}

export interface ImportRow {
  id: string
  row_number: number
  external_id: string | null
  payload: Record<string, unknown>
  status: ImportRowStatus
  message: string | null
  result_type: string | null
  result_id: string | null
}

export interface ImportBatch {
  id: string
  kind: ImportKind
  filename: string
  status: ImportBatchStatus
  mapping: Record<string, string>
  options: {
    columns?: string[]
    sheets?: string[]
    sheet?: string | null
    defaults?: Record<string, string>
  }
  summary: Partial<ImportSummary>
  confirmed_at: string | null
  created_at: string
}

export interface ImportBatchDetail extends ImportBatch {
  rows: Page<ImportRow>
}

export interface ImportSettings {
  toronja: {
    bank_account_id: string | null
    processor_account_id: string | null
    receivable_customer_id: string | null
    income_category_id: string | null
  }
}

export type HistoryAction = 'CREATE' | 'UPDATE' | 'CANCEL' | 'PAY' | 'APPROVE' | 'REJECT' | 'DELETE'
export type HistoryEntityType =
  | 'expense'
  | 'income'
  | 'payable'
  | 'receivable'
  | 'financial_account'
  | 'category'
  | 'proposal'

export interface HistoryFieldChange {
  field: string
  /** Nombre amigable en español ("Monto", "Categoría"). */
  label: string
  kind: 'money' | 'date' | 'text' | 'status' | 'bool' | 'rate' | 'ref'
  old: string | number | boolean | null
  new: string | number | boolean | null
  /** Referencias (categoría, cuenta…) ya resueltas a su nombre por el backend. */
  old_display: string | null
  new_display: string | null
}

export interface HistoryEvent {
  id: string
  entity_type: HistoryEntityType
  entity_id: string
  entity_label: string | null
  action: HistoryAction
  source: 'web' | 'assistant' | 'agent' | 'import' | 'approval' | 'system'
  reason: string | null
  user_id: string | null
  user_name: string | null
  created_at: string
  changes: HistoryFieldChange[]
}
