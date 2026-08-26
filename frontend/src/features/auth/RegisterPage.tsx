import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { AuthShell } from '@/features/auth/AuthShell'
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
  // El momento wow del §30: la empresa nace CON contabilidad, y se enseña.
  const [born, setBorn] = useState<{
    accounts: number | null
    folio: string | null
    balanced: boolean | null
  } | null>(null)

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
      // Antes de aterrizar en un tablero vacío, un vistazo a lo que acaba de
      // nacer por debajo. Si algo falla, se entra directo: el wow es opcional.
      try {
        const [accounts, entries, balance] = await Promise.all([
          api.get<unknown[]>('/accounting/accounts'),
          api.get<{ items: { folio: string }[] }>('/accounting/journal-entries', {
            params: { limit: 1 },
          }),
          api.get<{ total_debit: string; total_credit: string }>('/accounting/trial-balance'),
        ])
        setBorn({
          accounts: accounts.data.length,
          folio: entries.data.items[0]?.folio ?? null,
          balanced: Number(balance.data.total_debit) === Number(balance.data.total_credit),
        })
      } catch {
        navigate('/')
      }
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
          placeholder="Consultoría Aurora"
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

  if (born) {
    return (
      <AuthShell>
        <div className="text-center">
          <p className="figures text-[10px] uppercase tracking-[0.2em] text-accent">
            {form.business_name}
          </p>
          <h1 className="mt-2 font-display text-xl font-bold tracking-tight">
            Tu contabilidad ya existe
          </h1>
          <p className="mt-2 text-sm text-muted">
            No llenaste un solo campo contable, y aun así:
          </p>
        </div>
        <ul className="mt-5 space-y-2.5 text-sm">
          <li className="flex items-center justify-between rounded-lg border border-border bg-surface-2/50 px-4 py-2.5">
            <span>Catálogo de cuentas listo</span>
            <span className="figures font-semibold">{born.accounts} cuentas</span>
          </li>
          {born.folio ? (
            <li className="flex items-center justify-between rounded-lg border border-border bg-surface-2/50 px-4 py-2.5">
              <span>Póliza de apertura</span>
              <span className="figures font-semibold">{born.folio}</span>
            </li>
          ) : null}
          {born.balanced ? (
            <li className="flex items-center justify-between rounded-lg border border-border bg-surface-2/50 px-4 py-2.5">
              <span>Balanza de comprobación</span>
              <span className="font-medium text-pos">cargos = abonos ✓</span>
            </li>
          ) : null}
        </ul>
        <p className="mt-4 text-center text-xs text-muted">
          Cada operación que registres generará su póliza de partida doble, sola.
        </p>
        <Button className="mt-5 h-11 w-full hover:shadow-accent" onClick={() => navigate('/')}>
          Entrar a mi tablero
        </Button>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      footer={
        <>
          ¿Ya tienes cuenta?{' '}
          <Link to="/login" className="font-medium text-rail-ink hover:text-accent">
            Entra aquí
          </Link>
        </>
      }
    >
      <div className="flex items-center gap-3">
        <div className="flex flex-1 gap-1.5">
          {steps.map((_, index) => (
            <div
              key={index}
              className={`h-1 flex-1 rounded-full transition-colors ${
                index <= step ? 'bg-accent' : 'bg-surface-2'
              }`}
            />
          ))}
        </div>
        <span className="figures text-[10px] uppercase tracking-widest text-muted">
          {step + 1}/{steps.length}
        </span>
      </div>

      <h1 className="mt-5 font-display text-lg font-bold tracking-tight">{current.title}</h1>
      {step === 0 ? (
        <p className="mt-1 text-sm text-muted">
          Registras lo que pasa en tu negocio; ARCA lleva las finanzas y la contabilidad.
        </p>
      ) : null}

      <form
        onSubmit={(event) => {
          event.preventDefault()
          if (isLast) void submit()
          else setStep(step + 1)
        }}
        className="mt-5 space-y-4"
      >
        {current.body}
        {error ? (
          <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
            {error}
          </p>
        ) : null}
        <div className="flex items-center justify-between gap-3 pt-1">
          {step > 0 ? (
            <Button variant="ghost" onClick={() => setStep(step - 1)}>
              Atrás
            </Button>
          ) : (
            <span />
          )}
          <Button type="submit" className="h-11 hover:shadow-accent" disabled={!current.valid || loading}>
            {isLast ? (loading ? 'Creando…' : 'Crear mi empresa') : 'Continuar'}
          </Button>
        </div>
      </form>
    </AuthShell>
  )
}
