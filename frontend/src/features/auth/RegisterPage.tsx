import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import type { AuthResponse } from '@/types/api'

const BUSINESS_TYPES = [
  { value: 'commerce', label: 'Comercio / ventas' },
  { value: 'services', label: 'Servicios' },
  { value: 'restaurant', label: 'Restaurante / alimentos' },
  { value: 'manufacturing', label: 'Producción / taller' },
  { value: 'other', label: 'Otro' },
]

/** Onboarding §30: pasos cortos; ARCA configura catálogo y cuenta inicial por debajo. */
export function RegisterPage() {
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const [step, setStep] = useState(0)
  const [form, setForm] = useState({
    business_name: '',
    business_type: '',
    initial_cash: '',
    name: '',
    email: '',
    password: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  function update(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function submit() {
    setError(null)
    setLoading(true)
    try {
      const payload: Record<string, unknown> = {
        email: form.email,
        password: form.password,
        name: form.name,
        business_name: form.business_name,
        business_type: form.business_type || null,
      }
      if (form.initial_cash) payload.initial_cash = form.initial_cash
      const { data } = await api.post<AuthResponse>('/auth/register', payload)
      setSession(data)
      navigate('/')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  const steps = [
    {
      title: '¿Cómo se llama tu negocio?',
      valid: form.business_name.trim().length > 0,
      body: (
        <TextInput
          label="Nombre del negocio"
          required
          autoFocus
          placeholder="Taquería La Central"
          value={form.business_name}
          onChange={(event) => update('business_name', event.target.value)}
        />
      ),
    },
    {
      title: '¿A qué se dedica?',
      valid: true,
      body: (
        <SelectInput
          label="Giro"
          placeholder="Elige una opción (opcional)"
          options={BUSINESS_TYPES}
          value={form.business_type}
          onChange={(event) => update('business_type', event.target.value)}
        />
      ),
    },
    {
      title: '¿Con cuánto dinero inicia ARCA?',
      valid: true,
      body: (
        <TextInput
          label="Efectivo disponible hoy"
          type="number"
          min="0"
          step="0.01"
          placeholder="0.00"
          hint="Opcional. Puedes agregar tus cuentas de banco después."
          value={form.initial_cash}
          onChange={(event) => update('initial_cash', event.target.value)}
        />
      ),
    },
    {
      title: 'Crea tu acceso',
      valid: form.name.trim().length > 0 && form.email.includes('@') && form.password.length >= 8,
      body: (
        <div className="space-y-4">
          <TextInput label="Tu nombre" required value={form.name} onChange={(event) => update('name', event.target.value)} />
          <TextInput
            label="Correo"
            type="email"
            required
            autoComplete="email"
            value={form.email}
            onChange={(event) => update('email', event.target.value)}
          />
          <TextInput
            label="Contraseña"
            type="password"
            required
            autoComplete="new-password"
            hint="Mínimo 8 caracteres."
            value={form.password}
            onChange={(event) => update('password', event.target.value)}
          />
        </div>
      ),
    },
  ]

  const current = steps[step]
  const isLast = step === steps.length - 1

  return (
    <div className="flex min-h-full items-center justify-center bg-rail px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="font-display text-3xl font-bold tracking-tight text-white">ARCA</div>
          <p className="mt-2 text-sm text-rail-muted">
            Registra lo que pasa en tu negocio; ARCA hace las finanzas y la contabilidad.
          </p>
        </div>
        <div className="rounded-xl bg-surface p-6 shadow-float">
          <div className="mb-5 flex gap-1.5">
            {steps.map((_, index) => (
              <div
                key={index}
                className={`h-1 flex-1 rounded-full ${index <= step ? 'bg-accent' : 'bg-surface-2'}`}
              />
            ))}
          </div>
          <h1 className="mb-4 font-display text-xl font-semibold">{current.title}</h1>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              if (isLast) void submit()
              else setStep(step + 1)
            }}
            className="space-y-4"
          >
            {current.body}
            {error ? <p className="text-sm text-neg">{error}</p> : null}
            <div className="flex items-center justify-between pt-1">
              {step > 0 ? (
                <Button variant="ghost" onClick={() => setStep(step - 1)}>
                  Atrás
                </Button>
              ) : (
                <span />
              )}
              <Button type="submit" disabled={!current.valid || loading}>
                {isLast ? (loading ? 'Creando…' : 'Crear mi empresa') : 'Continuar'}
              </Button>
            </div>
          </form>
        </div>
        <p className="mt-4 text-center text-sm text-rail-muted">
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" className="font-medium text-white hover:underline">
            Entra aquí
          </Link>
        </p>
      </div>
    </div>
  )
}
