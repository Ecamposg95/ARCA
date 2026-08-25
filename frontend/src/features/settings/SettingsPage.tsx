import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card } from '@/components/ui/Table'
import { useAuthStore } from '@/stores/authStore'
import type { AgentKey, Organization } from '@/types/api'

export function SettingsPage() {
  const { organization, user } = useAuthStore()
  const [form, setForm] = useState({
    name: organization?.name ?? '',
    legal_name: organization?.legal_name ?? '',
    tax_id: organization?.tax_id ?? '',
  })
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { name: form.name }
      if (form.legal_name) payload.legal_name = form.legal_name
      if (form.tax_id) payload.tax_id = form.tax_id
      return (await api.patch<Organization>('/organizations/current', payload)).data
    },
    onSuccess: (updated) => {
      useAuthStore.setState({ organization: updated })
      setError(null)
      setMessage('Cambios guardados.')
    },
    onError: (err) => {
      setMessage(null)
      setError(errorMessage(err))
    },
  })

  return (
    <div>
      <PageHeader title="Configuración" description="Los datos de tu empresa." />
      <Card className="max-w-lg">
        <form
          onSubmit={(event) => {
            event.preventDefault()
            saveMutation.mutate()
          }}
          className="space-y-4"
        >
          <TextInput
            label="Nombre del negocio"
            required
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <TextInput
            label="Razón social"
            value={form.legal_name}
            onChange={(event) => setForm({ ...form, legal_name: event.target.value })}
          />
          <TextInput
            label="RFC"
            value={form.tax_id}
            onChange={(event) => setForm({ ...form, tax_id: event.target.value })}
          />
          <div className="text-xs text-muted">
            Moneda: {organization?.currency} · País: {organization?.country} · Usuario: {user?.email}
          </div>
          {message ? <p className="text-sm text-pos">{message}</p> : null}
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <Button type="submit" disabled={saveMutation.isPending}>
            Guardar cambios
          </Button>
        </form>
      </Card>

      <AgentKeysSection />
    </div>
  )
}

function AgentKeysSection() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ name: '', scopes: 'READ' })
  const [createdToken, setCreatedToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: keys } = useQuery({
    queryKey: ['agent-keys'],
    queryFn: async () => (await api.get<AgentKey[]>('/agent-keys')).data,
  })

  const createMutation = useMutation({
    mutationFn: async () => (await api.post<AgentKey>('/agent-keys', form)).data,
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ['agent-keys'] })
      setCreatedToken(created.token ?? null)
      setForm({ name: '', scopes: 'READ' })
      setError(null)
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const revokeMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/agent-keys/${id}`)
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['agent-keys'] }),
    onError: (err) => window.alert(errorMessage(err)),
  })

  return (
    <Card className="mt-6 max-w-lg">
      <h2 className="font-display text-lg font-semibold">Agentes</h2>
      <p className="mt-1 text-sm text-muted">
        Llaves para que agentes de IA lean tus números y propongan operaciones. Los agentes nunca
        registran nada: tú apruebas cada propuesta.
      </p>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          createMutation.mutate()
        }}
        className="mt-4 space-y-3"
      >
        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="Nombre del agente"
            required
            placeholder="Claude — mi asistente"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <SelectInput
            label="Permisos"
            options={[
              { value: 'READ', label: 'Solo lectura' },
              { value: 'READ,PROPOSE', label: 'Lectura + proponer' },
            ]}
            value={form.scopes}
            onChange={(event) => setForm({ ...form, scopes: event.target.value })}
          />
        </div>
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <Button type="submit" disabled={createMutation.isPending}>
          Crear llave
        </Button>
      </form>

      {(keys ?? []).length > 0 ? (
        <ul className="mt-5 divide-y divide-border">
          {(keys ?? []).map((key) => (
            <li key={key.id} className="flex items-center justify-between py-2.5 text-sm">
              <div>
                <span className={key.active ? 'font-medium' : 'font-medium text-muted line-through'}>
                  {key.name}
                </span>
                <span className="figures ml-2 text-xs text-muted">{key.key_prefix}…</span>
                <span className="ml-2 text-xs text-muted">
                  {key.scopes === 'READ' ? 'lectura' : 'lectura + proponer'}
                </span>
              </div>
              {key.active ? (
                <Button
                  variant="ghost"
                  className="!px-2 !py-1 text-xs"
                  onClick={() => {
                    if (window.confirm(`¿Revocar la llave "${key.name}"? El agente perderá acceso.`))
                      revokeMutation.mutate(key.id)
                  }}
                >
                  Revocar
                </Button>
              ) : (
                <span className="text-xs text-muted">Revocada</span>
              )}
            </li>
          ))}
        </ul>
      ) : null}

      <Modal title="Guarda tu llave" open={createdToken !== null} onClose={() => setCreatedToken(null)}>
        <p className="text-sm text-muted">
          Esta es la única vez que verás la llave completa. Cópiala y guárdala en un lugar seguro.
        </p>
        <div className="figures mt-3 break-all rounded-lg bg-surface-2 p-3 text-sm">{createdToken}</div>
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              if (createdToken) void navigator.clipboard.writeText(createdToken)
            }}
          >
            Copiar
          </Button>
          <Button onClick={() => setCreatedToken(null)}>Listo, la guardé</Button>
        </div>
      </Modal>
    </Card>
  )
}
