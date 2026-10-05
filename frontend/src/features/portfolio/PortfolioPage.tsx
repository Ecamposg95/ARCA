/** Mis empresas: la cartera de quien lleva varias contabilidades. Una fila por
 *  empresa, lo urgente arriba, y el porqué del semáforo escrito en la fila. */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table } from '@/components/ui/Table'
import { loadCompanies, switchCompany } from '@/lib/companies'
import { useAuthStore } from '@/stores/authStore'
import type { Organization, Page, PortfolioItem, PortfolioStatus } from '@/types/api'

const STATUS: Record<PortfolioStatus, { label: string; dot: string; text: string }> = {
  red: { label: 'Urgente', dot: 'bg-neg', text: 'text-neg' },
  amber: { label: 'Por atender', dot: 'bg-warn', text: 'text-warn' },
  green: { label: 'Al corriente', dot: 'bg-pos', text: 'text-pos' },
}

const ROLE_LABELS: Record<string, string> = {
  OWNER: 'Dueño',
  ADMIN: 'Administrador',
  ACCOUNTANT: 'Contador',
  MEMBER: 'Captura',
  VIEWER: 'Consulta',
}

const EMPTY_FORM = { business_name: '', tax_id: '', initial_cash: '' }

function formatPeriod(period: string | null): string {
  if (!period) return 'Ninguno'
  const [year, month] = period.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('es-MX', {
    month: 'short',
    year: 'numeric',
  })
}

/** "1 urgente · 2 por atender · 1 al corriente": el resumen que se lee de un vistazo. */
function summarize(items: PortfolioItem[]): string {
  const count = (status: PortfolioStatus) => items.filter((item) => item.status === status).length
  const red = count('red')
  const amber = count('amber')
  const green = count('green')
  return [
    red ? `${red} ${red === 1 ? 'urgente' : 'urgentes'}` : null,
    amber ? `${amber} por atender` : null,
    green ? `${green} al corriente` : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

const right = (label: string) => <span className="block text-right">{label}</span>

export function PortfolioPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const active = useAuthStore((state) => state.organization)
  const organizations = useAuthStore((state) => state.organizations)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [formError, setFormError] = useState<string | null>(null)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['portfolio'],
    queryFn: async () => (await api.get<Page<PortfolioItem>>('/portfolio')).data.items,
    // Sin caché: se vuelve aquí justo después de cerrar un mes o pagar un
    // vencido dentro de una empresa, y el semáforo viejo sería mentira.
    staleTime: 0,
    gcTime: 0,
  })

  const create = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { business_name: form.business_name }
      if (form.tax_id.trim()) payload.tax_id = form.tax_id.trim()
      if (form.initial_cash) payload.initial_cash = form.initial_cash
      return (await api.post<Organization>('/organizations', payload)).data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['portfolio'] })
      void queryClient.invalidateQueries({ queryKey: ['me'] })
      setCreating(false)
      setForm(EMPTY_FORM)
      setFormError(null)
    },
    onError: (err) => setFormError(errorMessage(err)),
  })

  async function open(item: PortfolioItem) {
    // La lista de la sesión puede ir un paso atrás de la cartera (empresa recién
    // creada): si no está, se vuelve a pedir antes de entrar.
    const company =
      organizations.find((candidate) => candidate.id === item.organization_id) ??
      (await loadCompanies()).organizations.find(
        (candidate) => candidate.id === item.organization_id,
      )
    if (!company) return
    if (company.id !== active?.id) switchCompany(company)
    navigate('/')
  }

  const items = data ?? []

  return (
    <>
      <PageHeader
        title="Mis empresas"
        description={
          items.length > 0
            ? `${items.length} ${items.length === 1 ? 'empresa' : 'empresas'} · ${summarize(items)}`
            : 'Todas las empresas que llevas, en un solo lugar.'
        }
        actions={<Button onClick={() => setCreating(true)}>+ Nueva empresa</Button>}
      />

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : error ? (
        <EmptyState
          title="No pudimos cargar tus empresas"
          message={errorMessage(error)}
          action={<Button onClick={() => void refetch()}>Reintentar</Button>}
        />
      ) : (
        <Table
          headers={[
            'Empresa',
            'Estado',
            right('Caja'),
            right('Por cobrar'),
            right('Vencido por pagar'),
            'Último cierre',
            right('Propuestas'),
          ]}
          secondary={[4, 5, 6, 7]}
        >
          {items.map((item) => {
            const status = STATUS[item.status]
            const overdue = Number(item.payable_overdue) > 0
            return (
              <tr
                key={item.organization_id}
                className="cursor-pointer align-top transition-colors hover:bg-surface-2/60"
                onClick={() => void open(item)}
              >
                <td className="px-4 py-3">
                  {/* El botón hace la fila alcanzable con teclado; el clic en
                      cualquier otra celda es un atajo de ratón. */}
                  <button
                    type="button"
                    className="text-left font-medium hover:text-accent"
                    onClick={(event) => {
                      event.stopPropagation()
                      void open(item)
                    }}
                  >
                    {item.name}
                  </button>
                  <div className="mt-0.5 text-xs text-muted">
                    <span className="figures">{item.tax_id ?? 'Sin RFC'}</span>
                    {' · '}
                    {ROLE_LABELS[item.role] ?? item.role}
                    {item.organization_id === active?.id ? ' · abierta' : null}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold ${status.text}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden />
                    {status.label}
                  </span>
                  {item.reasons.map((reason) => (
                    <div key={reason} className="mt-0.5 text-xs text-muted">
                      {reason}
                    </div>
                  ))}
                </td>
                <td className="px-4 py-3 text-right">
                  <Money value={item.cash} size="sm" />
                </td>
                <td className="px-4 py-3 text-right">
                  <Money value={item.receivable} size="sm" />
                </td>
                <td className="px-4 py-3 text-right">
                  <Money value={item.payable_overdue} size="sm" tone={overdue ? 'neg' : 'muted'} />
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-muted">
                  {formatPeriod(item.last_closed_period)}
                </td>
                <td className="figures px-4 py-3 text-right">
                  {item.pending_proposals > 0 ? item.pending_proposals : '—'}
                </td>
              </tr>
            )
          })}
        </Table>
      )}

      {!isLoading && !error && items.length === 1 ? (
        <p className="mt-4 text-sm text-muted">
          Hoy llevas una sola empresa. Si llevas la contabilidad de otras, agrégalas aquí y cambia
          entre ellas sin cerrar sesión.
        </p>
      ) : null}

      <Modal title="Nueva empresa" open={creating} onClose={() => setCreating(false)}>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            create.mutate()
          }}
        >
          <TextInput
            label="Nombre de la empresa"
            required
            autoFocus
            placeholder="Ferretería El Tornillo"
            value={form.business_name}
            onChange={(event) => setForm({ ...form, business_name: event.target.value })}
          />
          <TextInput
            label="RFC (opcional)"
            placeholder="FET180312AB1"
            maxLength={13}
            value={form.tax_id}
            onChange={(event) => setForm({ ...form, tax_id: event.target.value.toUpperCase() })}
          />
          <TextInput
            label="Dinero en caja al empezar (opcional)"
            type="number"
            min="0"
            step="0.01"
            inputMode="decimal"
            placeholder="0.00"
            hint="ARCA crea su catálogo contable, sus categorías y la cuenta Caja con este saldo."
            value={form.initial_cash}
            onChange={(event) => setForm({ ...form, initial_cash: event.target.value })}
          />
          {formError ? (
            <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
              {formError}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creando…' : 'Crear empresa'}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  )
}
