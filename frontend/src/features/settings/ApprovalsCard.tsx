/** Autorización por monto: umbral de la empresa y límite del auxiliar. La
 *  facultad de cada miembro se enciende en la tarjeta de Equipo. */

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { Card } from '@/components/ui/Table'
import type { ApprovalSettings } from '@/types/api'

export function ApprovalsCard() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState({ approval_threshold: '', member_capture_limit: '' })
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data } = useQuery({
    queryKey: ['approval-settings'],
    queryFn: async () => (await api.get<ApprovalSettings>('/organizations/current/approvals')).data,
  })

  useEffect(() => {
    if (!data) return
    setForm({
      approval_threshold: data.approval_threshold ?? '',
      member_capture_limit: data.member_capture_limit ?? '',
    })
  }, [data])

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.patch<ApprovalSettings>('/organizations/current/approvals', {
          approval_threshold: form.approval_threshold.trim() || null,
          member_capture_limit: form.member_capture_limit.trim() || null,
        })
      ).data,
    onSuccess: (saved) => {
      queryClient.setQueryData(['approval-settings'], saved)
      setError(null)
      setMessage(
        saved.approval_threshold
          ? 'Guardado. Lo que alcance el umbral esperará autorización.'
          : 'Guardado. Sin umbral, todo se registra directo.',
      )
    },
    onError: (err) => {
      setMessage(null)
      setError(errorMessage(err))
    },
  })

  return (
    <Card className="mt-6 max-w-lg">
      <h2 className="font-display text-lg font-semibold">Autorizaciones</h2>
      <p className="mt-1 text-sm text-muted">
        Lo que alcance el umbral se envía a quien autoriza antes de registrarse. Quién autoriza se
        decide en Equipo; el dueño siempre.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate()
        }}
        className="mt-4 space-y-3"
      >
        <TextInput
          label="Umbral de autorización (vacío = sin autorización)"
          type="number"
          min="0.01"
          step="0.01"
          inputMode="decimal"
          placeholder="100000"
          value={form.approval_threshold}
          onChange={(event) => setForm({ ...form, approval_threshold: event.target.value })}
          hint="Gastos pagados, pagos a proveedores y traspasos de este monto o más esperan autorización."
        />
        <TextInput
          label="Límite de captura del auxiliar (vacío = sin límite)"
          type="number"
          min="0.01"
          step="0.01"
          inputMode="decimal"
          placeholder="2000"
          value={form.member_capture_limit}
          onChange={(event) => setForm({ ...form, member_capture_limit: event.target.value })}
          hint='Quien "registra operaciones" no puede capturar por encima de esto; lo que lo supere lo captura un administrador.'
        />
        {message ? <p className="text-sm text-pos">{message}</p> : null}
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <Button type="submit" disabled={save.isPending}>
          Guardar
        </Button>
      </form>
    </Card>
  )
}
