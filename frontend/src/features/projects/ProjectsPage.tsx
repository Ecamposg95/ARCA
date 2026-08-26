/** Proyectos: cuál trabajo deja dinero y cuál se lo come.
 *
 *  El margen se mide sobre subtotales, sin IVA: el impuesto no es tuyo, así que
 *  contarlo como ingreso haría ver rentable lo que no lo es.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { Money } from '@/components/ui/Money'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card, Table } from '@/components/ui/Table'
import { formatMoney } from '@/lib/format'
import { useContacts } from '@/lib/hooks'
import type { ProjectsResponse } from '@/types/api'

export function ProjectsPage() {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(searchParams.has('nuevo'))
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '',
    code: '',
    customer_id: '',
    budget: '',
    start_date: '',
    end_date: '',
  })

  const { data: customers } = useContacts('customers')
  const { data, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: async () => (await api.get<ProjectsResponse>('/projects')).data,
  })

  const createProject = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = { name: form.name }
      if (form.code) payload.code = form.code
      if (form.customer_id) payload.customer_id = form.customer_id
      if (form.budget) payload.budget = form.budget
      if (form.start_date) payload.start_date = form.start_date
      if (form.end_date) payload.end_date = form.end_date
      await api.post('/projects', payload)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      closeModal()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function closeModal() {
    setModalOpen(false)
    setError(null)
    setForm({ name: '', code: '', customer_id: '', budget: '', start_date: '', end_date: '' })
    if (searchParams.has('nuevo')) {
      searchParams.delete('nuevo')
      setSearchParams(searchParams, { replace: true })
    }
  }

  const projects = data?.items ?? []
  const unassigned = data?.unassigned
  const customerName = (id: string | null) =>
    id ? ((customers ?? []).find((c) => c.id === id)?.name ?? '—') : '—'

  return (
    <div>
      <PageHeader
        title="Proyectos"
        description="Qué trabajo deja dinero y cuál se lo come."
        actions={<Button onClick={() => setModalOpen(true)}>+ Nuevo proyecto</Button>}
      />

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : projects.length === 0 ? (
        <EmptyState
          title="Sin proyectos todavía"
          message="Marca tus ingresos y gastos con un proyecto para saber cuál te deja dinero. No cambia tu contabilidad: es una etiqueta para entender el negocio."
          action={<Button onClick={() => setModalOpen(true)}>Nuevo proyecto</Button>}
        />
      ) : (
        <div className="space-y-4">
          <Table
            headers={[
              'Proyecto',
              'Cliente',
              <span key="i" className="block text-right">
                Ingresos
              </span>,
              <span key="c" className="block text-right">
                Costos
              </span>,
              <span key="m" className="block text-right">
                Margen
              </span>,
              <span key="p" className="block text-right">
                %
              </span>,
            ]}
            secondary={[2, 4]}
          >
            {projects.map((project) => {
              const margin = Number(project.margin)
              return (
                <tr key={project.id} className="hover:bg-surface-2/50">
                  <td className="px-4 py-2.5">
                    <div className="font-medium">{project.name}</div>
                    {project.budget ? (
                      <div className="text-xs text-muted">
                        {formatMoney(project.budget)} acordados
                        {project.budget_used_pct !== null
                          ? ` · ${project.budget_used_pct}% facturado`
                          : ''}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-2.5 text-muted">{customerName(project.customer_id)}</td>
                  <td className="figures px-4 py-2.5 text-right">
                    {formatMoney(project.revenue)}
                  </td>
                  <td className="figures px-4 py-2.5 text-right text-muted">
                    {formatMoney(project.cost)}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Money value={project.margin} tone={margin < 0 ? 'neg' : 'pos'} />
                  </td>
                  <td
                    className={`figures px-4 py-2.5 text-right ${margin < 0 ? 'text-neg' : 'text-muted'}`}
                  >
                    {project.margin_pct}%
                  </td>
                </tr>
              )
            })}
          </Table>

          {unassigned && Number(unassigned.revenue) + Number(unassigned.cost) > 0 ? (
            <Card>
              <p className="text-xs uppercase tracking-wider text-muted">Sin proyecto asignado</p>
              <div className="mt-2 flex flex-wrap gap-x-8 gap-y-2 text-sm">
                <span>
                  Ingresos <span className="figures">{formatMoney(unassigned.revenue)}</span>
                </span>
                <span>
                  Costos <span className="figures">{formatMoney(unassigned.cost)}</span>
                </span>
                <span>
                  Margen <span className="figures">{formatMoney(unassigned.margin)}</span>
                </span>
              </div>
              <p className="mt-2 text-xs text-muted">
                Esta parte del negocio todavía no se mide por proyecto.
              </p>
            </Card>
          ) : null}
        </div>
      )}

      <Modal title="Nuevo proyecto" open={modalOpen} onClose={closeModal}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            createProject.mutate()
          }}
          className="space-y-3"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <TextInput
            label="Nombre del proyecto"
            placeholder="ERP fase 2 — Grupo Industrial"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            required
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Clave (opcional)"
              placeholder="P-2026-014"
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value })}
            />
            <TextInput
              label="Monto acordado (opcional)"
              type="number"
              step="0.01"
              value={form.budget}
              onChange={(event) => setForm({ ...form, budget: event.target.value })}
            />
          </div>
          <SelectInput
            label="Cliente (opcional)"
            value={form.customer_id}
            onChange={(event) => setForm({ ...form, customer_id: event.target.value })}
            options={[
              { value: '', label: 'Sin cliente' },
              ...(customers ?? []).map((c) => ({ value: c.id, label: c.name })),
            ]}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Empieza (opcional)"
              type="date"
              value={form.start_date}
              onChange={(event) => setForm({ ...form, start_date: event.target.value })}
            />
            <TextInput
              label="Termina (opcional)"
              type="date"
              value={form.end_date}
              onChange={(event) => setForm({ ...form, end_date: event.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={closeModal}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createProject.isPending}>
              Crear proyecto
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
