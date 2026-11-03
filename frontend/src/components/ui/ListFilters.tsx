/** Filtros finos de las listas de operaciones y su descarga a Excel.
 *
 *  Compartidos por Gastos, Ingresos y Movimientos para que los tres se filtren
 *  igual y la descarga baje exactamente lo que se ve. */

import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { FilterChip } from '@/components/ui/TableTools'
import { downloadErrorMessage, downloadFile } from '@/lib/download'
import { useAccounts, useMembers } from '@/lib/hooks'
import { toast } from '@/stores/toastStore'

/** Todas las formas de pago que conoce el backend: filtrar por "Tarjeta"
 *  debe encontrar lo que importó Toronja aunque el formulario no la ofrezca. */
export const PAYMENT_METHOD_FILTER_OPTIONS = [
  { value: 'EFECTIVO', label: 'Efectivo' },
  { value: 'TRANSFERENCIA', label: 'Transferencia' },
  { value: 'TARJETA_DEBITO', label: 'Tarjeta de débito' },
  { value: 'TARJETA_CREDITO', label: 'Tarjeta de crédito' },
  { value: 'TARJETA', label: 'Tarjeta' },
  { value: 'DOMICILIACION', label: 'Domiciliación' },
  { value: 'CHEQUE', label: 'Cheque' },
  { value: 'PASARELA', label: 'Pasarela de pago' },
  { value: 'OTRO', label: 'Otro' },
]

export interface FineFilterValues {
  category_id: string
  financial_account_id: string
  payment_method: string
  created_by: string
  contact: string
  min_amount: string
  max_amount: string
}

export const EMPTY_FINE_FILTERS: FineFilterValues = {
  category_id: '',
  financial_account_id: '',
  payment_method: '',
  created_by: '',
  contact: '',
  min_amount: '',
  max_amount: '',
}

export function countFineFilters(value: FineFilterValues): number {
  return (
    Number(Boolean(value.category_id)) +
    Number(Boolean(value.financial_account_id)) +
    Number(Boolean(value.payment_method)) +
    Number(Boolean(value.created_by)) +
    Number(Boolean(value.contact)) +
    Number(Boolean(value.min_amount || value.max_amount))
  )
}

/** Querystring: sólo lo que tiene valor. `value` puede traer más campos (el
 *  resto de los filtros de la página); aquí sólo se leen los finos. */
export function fineFilterParams(value: FineFilterValues): Record<string, string> {
  const keys = Object.keys(EMPTY_FINE_FILTERS) as (keyof FineFilterValues)[]
  return Object.fromEntries(keys.filter((key) => value[key] !== '').map((key) => [key, value[key]]))
}

interface Option {
  id: string
  name: string
}

const selectClass = 'rounded-lg border border-border bg-surface px-2 py-1.5 text-sm'

/** Los selectores finos. Categoría y contacto son opcionales: Movimientos
 *  mezcla entradas y salidas y no siempre tiene sentido ofrecerlos. */
export function FineFilterSelects({
  value,
  onChange,
  categories,
  contacts,
  contactPlaceholder = 'Todos los contactos',
  accounts: showAccounts = true,
}: {
  value: FineFilterValues
  onChange: (next: Partial<FineFilterValues>) => void
  categories?: Option[]
  contacts?: Option[]
  contactPlaceholder?: string
  accounts?: boolean
}) {
  const { data: accounts } = useAccounts()
  const { data: members } = useMembers()
  return (
    <>
      {categories && categories.length > 0 ? (
        <select
          aria-label="Categoría"
          value={value.category_id}
          onChange={(event) => onChange({ category_id: event.target.value })}
          className={selectClass}
        >
          <option value="">Todas las categorías</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      ) : null}
      {showAccounts && (accounts ?? []).length > 1 ? (
        <select
          aria-label="Cuenta"
          value={value.financial_account_id}
          onChange={(event) => onChange({ financial_account_id: event.target.value })}
          className={selectClass}
        >
          <option value="">Todas las cuentas</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </select>
      ) : null}
      <select
        aria-label="Forma de pago"
        value={value.payment_method}
        onChange={(event) => onChange({ payment_method: event.target.value })}
        className={selectClass}
      >
        <option value="">Cualquier forma de pago</option>
        {PAYMENT_METHOD_FILTER_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {contacts && contacts.length > 0 ? (
        <select
          aria-label="Proveedor o cliente"
          value={value.contact}
          onChange={(event) => onChange({ contact: event.target.value })}
          className={selectClass}
        >
          <option value="">{contactPlaceholder}</option>
          {contacts.map((contact) => (
            <option key={contact.id} value={contact.id}>
              {contact.name}
            </option>
          ))}
        </select>
      ) : null}
      {(members ?? []).length > 1 ? (
        <select
          aria-label="Registró"
          value={value.created_by}
          onChange={(event) => onChange({ created_by: event.target.value })}
          className={selectClass}
        >
          <option value="">Lo registró cualquiera</option>
          {(members ?? []).map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.name}
            </option>
          ))}
        </select>
      ) : null}
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <span>De $</span>
        <input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          aria-label="Monto mínimo"
          value={value.min_amount}
          onChange={(event) => onChange({ min_amount: event.target.value })}
          className="figures w-24 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
        />
        <span>a $</span>
        <input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          aria-label="Monto máximo"
          value={value.max_amount}
          onChange={(event) => onChange({ max_amount: event.target.value })}
          className="figures w-24 rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-ink"
        />
      </div>
    </>
  )
}

/** Chips de lo aplicado, con su nombre legible. */
export function FineFilterChips({
  value,
  onChange,
  categories,
  contacts,
}: {
  value: FineFilterValues
  onChange: (next: Partial<FineFilterValues>) => void
  categories?: Option[]
  contacts?: Option[]
}) {
  const { data: accounts } = useAccounts()
  const { data: members } = useMembers()
  const nameOf = (items: Option[] | undefined, id: string) =>
    items?.find((item) => item.id === id)?.name ?? '…'
  return (
    <>
      {value.category_id ? (
        <FilterChip
          label={`Categoría: ${nameOf(categories, value.category_id)}`}
          onRemove={() => onChange({ category_id: '' })}
        />
      ) : null}
      {value.financial_account_id ? (
        <FilterChip
          label={`Cuenta: ${nameOf(accounts, value.financial_account_id)}`}
          onRemove={() => onChange({ financial_account_id: '' })}
        />
      ) : null}
      {value.payment_method ? (
        <FilterChip
          label={
            PAYMENT_METHOD_FILTER_OPTIONS.find((option) => option.value === value.payment_method)
              ?.label ?? value.payment_method
          }
          onRemove={() => onChange({ payment_method: '' })}
        />
      ) : null}
      {value.contact ? (
        <FilterChip label={nameOf(contacts, value.contact)} onRemove={() => onChange({ contact: '' })} />
      ) : null}
      {value.created_by ? (
        <FilterChip
          label={`Registró: ${members?.find((member) => member.user_id === value.created_by)?.name ?? '…'}`}
          onRemove={() => onChange({ created_by: '' })}
        />
      ) : null}
      {value.min_amount || value.max_amount ? (
        <FilterChip
          label={`$${value.min_amount || '0'} – ${value.max_amount ? `$${value.max_amount}` : '∞'}`}
          onRemove={() => onChange({ min_amount: '', max_amount: '' })}
        />
      ) : null}
    </>
  )
}

/** "Descargar Excel" con los filtros de la lista. Va por el cliente de axios
 *  (blob) para que viaje el token de la sesión. */
export function DownloadExcelButton({
  path,
  params,
  fallbackName,
}: {
  path: string
  params: Record<string, string | number | boolean>
  fallbackName: string
}) {
  const [busy, setBusy] = useState(false)
  async function download() {
    setBusy(true)
    try {
      const clean = Object.fromEntries(
        Object.entries(params).map(([key, value]) => [key, typeof value === 'boolean' ? String(value) : value]),
      )
      await downloadFile(path, { ...clean, format: 'xlsx' }, fallbackName)
    } catch (error) {
      toast(await downloadErrorMessage(error), 'neg')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Button variant="secondary" onClick={() => void download()} disabled={busy}>
      {busy ? 'Preparando…' : 'Descargar Excel'}
    </Button>
  )
}
