/** Equipo: el backend distingue cinco roles desde el día uno; hasta ahora no
 *  había forma de asignarlos, así que ARCA era de un solo usuario en la práctica. */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Card } from '@/components/ui/Table'

interface Member {
  id: string
  user_id: string
  name: string
  email: string
  role: string
  is_you: boolean
}

/** Los nombres que ve el usuario dicen lo que la persona PUEDE HACER,
 *  no cómo se llama el rol en la base de datos. */
const ROLES = [
  { value: 'ADMIN', label: 'Administra todo', hint: 'Puede invitar gente y cambiar la empresa' },
  { value: 'ACCOUNTANT', label: 'Lleva la contabilidad', hint: 'Registra operaciones y ve pólizas' },
  { value: 'MEMBER', label: 'Registra operaciones', hint: 'Captura ingresos y gastos' },
  { value: 'VIEWER', label: 'Sólo mira', hint: 'Consulta sin poder cambiar nada' },
]

const ROLE_LABELS: Record<string, string> = {
  OWNER: 'Dueño',
  ...Object.fromEntries(ROLES.map((role) => [role.value, role.label])),
}

export function TeamCard() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    email: '',
    name: '',
    role: 'MEMBER',
    password: '',
  })

  const { data } = useQuery({
    queryKey: ['members'],
    queryFn: async () =>
      (await api.get<{ items: Member[] }>('/organizations/current/members')).data.items,
  })

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['members'] })
  }

  const invite = useMutation({
    mutationFn: async () => {
      await api.post('/organizations/current/members', form)
    },
    onSuccess: () => {
      invalidate()
      setOpen(false)
      setError(null)
      setForm({ email: '', name: '', role: 'MEMBER', password: '' })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const changeRole = useMutation({
    mutationFn: async ({ id, role }: { id: string; role: string }) => {
      await api.patch(`/organizations/current/members/${id}`, { role })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const remove = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/organizations/current/members/${id}`)
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  const members = data ?? []

  return (
    <Card className="mt-6 max-w-lg">
      <h2 className="font-display text-lg font-semibold">Equipo</h2>
      <p className="mt-1 text-sm text-muted">
        Quién entra a tu empresa y qué puede hacer. Tú decides el permiso de cada quien.
      </p>

      <div className="mt-4 divide-y divide-border">
        {members.map((member) => (
          <div key={member.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">
                {member.name}
                {member.is_you ? <span className="ml-2 text-xs text-muted">(tú)</span> : null}
              </p>
              <p className="truncate text-xs text-muted">{member.email}</p>
            </div>
            {member.role === 'OWNER' ? (
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">
                {ROLE_LABELS.OWNER}
              </span>
            ) : (
              <div className="flex items-center gap-2">
                <select
                  value={member.role}
                  onChange={(event) =>
                    changeRole.mutate({ id: member.id, role: event.target.value })
                  }
                  className="rounded-lg border border-border bg-surface px-2 py-1 text-xs"
                >
                  {ROLES.map((role) => (
                    <option key={role.value} value={role.value}>
                      {role.label}
                    </option>
                  ))}
                </select>
                <Button
                  variant="ghost"
                  className="!px-2 !py-1 text-xs"
                  onClick={() => {
                    if (window.confirm(`¿Sacar a ${member.name} de la empresa?`))
                      remove.mutate(member.id)
                  }}
                >
                  Quitar
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>

      {open ? (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            invite.mutate()
          }}
          className="mt-4 space-y-3 border-t border-border pt-4"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <TextInput
            label="Nombre"
            placeholder="María Contreras"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            required
          />
          <TextInput
            label="Correo"
            type="email"
            placeholder="maria@empresa.mx"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            required
          />
          <SelectInput
            label="¿Qué va a poder hacer?"
            value={form.role}
            onChange={(event) => setForm({ ...form, role: event.target.value })}
            options={ROLES.map((role) => ({ value: role.value, label: role.label }))}
          />
          <p className="text-xs text-muted">
            {ROLES.find((role) => role.value === form.role)?.hint}
          </p>
          <TextInput
            label="Contraseña inicial"
            type="password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            required
          />
          <p className="text-xs text-muted">
            ARCA todavía no manda correos: entrégale esta contraseña y pídele que la cambie.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={invite.isPending}>
              Agregar al equipo
            </Button>
          </div>
        </form>
      ) : (
        <Button variant="secondary" className="mt-4" onClick={() => setOpen(true)}>
          + Agregar a alguien
        </Button>
      )}
    </Card>
  )
}
