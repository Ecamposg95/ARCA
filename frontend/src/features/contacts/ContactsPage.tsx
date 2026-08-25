import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { PageHeader } from '@/components/ui/PageHeader'
import { Table } from '@/components/ui/Table'
import { TableFooter } from '@/components/ui/Pagination'
import type { Contact, Page } from '@/types/api'

interface Config {
  resource: 'customers' | 'vendors'
  title: string
  description: string
  singular: string
  emptyTitle: string
  emptyMessage: string
}

export const CUSTOMERS_CONFIG: Config = {
  resource: 'customers',
  title: 'Clientes',
  description: 'A quién le vendes.',
  singular: 'Cliente',
  emptyTitle: 'Aún no tienes clientes',
  emptyMessage: 'Da de alta a tus clientes para saber quién te compra y quién te debe.',
}

export const VENDORS_CONFIG: Config = {
  resource: 'vendors',
  title: 'Proveedores',
  description: 'A quién le compras.',
  singular: 'Proveedor',
  emptyTitle: 'Aún no tienes proveedores',
  emptyMessage: 'Da de alta a tus proveedores para saber a quién le compras y a quién le debes.',
}

const EMPTY_FORM = { name: '', legal_name: '', tax_id: '', email: '', phone: '', notes: '' }

export function ContactsPage({ config }: { config: Config }) {
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [modalOpen, setModalOpen] = useState(searchParams.has('nuevo'))
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: [config.resource, search, offset],
    queryFn: async () =>
      (
        await api.get<Page<Contact>>(`/${config.resource}`, {
          params: { ...(search ? { q: search } : {}), offset },
        })
      ).data,
  })

  const createMutation = useMutation({
    mutationFn: async () => {
      const payload = Object.fromEntries(Object.entries(form).filter(([, value]) => value !== ''))
      await api.post(`/${config.resource}`, payload)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [config.resource] })
      closeModal()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function closeModal() {
    setModalOpen(false)
    setForm(EMPTY_FORM)
    setError(null)
    if (searchParams.has('nuevo')) {
      searchParams.delete('nuevo')
      setSearchParams(searchParams, { replace: true })
    }
  }

  const items = data?.items ?? []

  return (
    <div>
      <PageHeader
        title={config.title}
        description={config.description}
        actions={<Button onClick={() => setModalOpen(true)}>+ {config.singular}</Button>}
      >
        <input
          type="search"
          placeholder={`Buscar ${config.title.toLowerCase()}…`}
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setOffset(0)
          }}
          className="w-full max-w-xs rounded border border-border bg-surface px-3 py-2 text-sm"
        />
      </PageHeader>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        <EmptyState
          title={config.emptyTitle}
          message={config.emptyMessage}
          action={<Button onClick={() => setModalOpen(true)}>Agregar {config.singular.toLowerCase()}</Button>}
        />
      ) : (
        <Table
          headers={['Nombre', 'RFC', 'Correo', 'Teléfono']}
          footer={<TableFooter page={data!} onOffsetChange={setOffset} noun={config.title.toLowerCase()} />}
        >
          {items.map((contact) => (
            <tr key={contact.id} className="hover:bg-surface-2/50">
              <td className="px-4 py-2.5">
                <div className="font-medium">{contact.name}</div>
                {contact.legal_name ? <div className="text-xs text-muted">{contact.legal_name}</div> : null}
              </td>
              <td className="px-4 py-2.5 text-muted">{contact.tax_id ?? '—'}</td>
              <td className="px-4 py-2.5 text-muted">{contact.email ?? '—'}</td>
              <td className="px-4 py-2.5 text-muted">{contact.phone ?? '—'}</td>
            </tr>
          ))}
        </Table>
      )}

      <Modal title={`Nuevo ${config.singular.toLowerCase()}`} open={modalOpen} onClose={closeModal}>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            createMutation.mutate()
          }}
          className="space-y-4"
        >
          <TextInput
            label="Nombre"
            required
            autoFocus
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Razón social (opcional)"
              value={form.legal_name}
              onChange={(event) => setForm({ ...form, legal_name: event.target.value })}
            />
            <TextInput
              label="RFC (opcional)"
              value={form.tax_id}
              onChange={(event) => setForm({ ...form, tax_id: event.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <TextInput
              label="Correo (opcional)"
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
            <TextInput
              label="Teléfono (opcional)"
              value={form.phone}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
            />
          </div>
          <TextInput
            label="Notas (opcional)"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={closeModal}>
              Cancelar
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              Guardar
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
