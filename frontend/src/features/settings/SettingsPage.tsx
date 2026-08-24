import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { PageHeader } from '@/components/ui/PageHeader'
import { Card } from '@/components/ui/Table'
import { useAuthStore } from '@/stores/authStore'
import type { Organization } from '@/types/api'

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
    </div>
  )
}
