import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Field'
import { AuthShell } from '@/features/auth/AuthShell'
import type { AuthResponse } from '@/types/api'

export function LoginPage() {
  const navigate = useNavigate()
  const setSession = useAuthStore((state) => state.setSession)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const { data } = await api.post<AuthResponse>('/auth/login', { email, password })
      setSession(data)
      navigate('/')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell
      footer={
        <>
          ¿Primera vez aquí?{' '}
          <Link to="/registro" className="font-medium text-rail-ink hover:text-accent">
            Crea tu empresa
          </Link>
        </>
      }
    >
      <h1 className="font-display text-lg font-bold tracking-tight">Entra a tu empresa</h1>

      <form onSubmit={onSubmit} className="mt-5 space-y-4">
        <TextInput
          label="Correo"
          type="email"
          required
          autoFocus
          autoComplete="email"
          placeholder="tu@empresa.mx"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <TextInput
          label="Contraseña"
          type={showPassword ? 'text' : 'password'}
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          action={
            <button
              type="button"
              onClick={() => setShowPassword((visible) => !visible)}
              className="rounded text-[11px] font-medium text-muted transition-colors hover:text-accent"
            >
              {showPassword ? 'Ocultar' : 'Mostrar'}
            </button>
          }
        />

        {error ? (
          <p role="alert" className="rounded border-l-2 border-neg bg-neg/10 px-3 py-2 text-sm text-neg">
            {error}
          </p>
        ) : null}

        <Button type="submit" className="h-11 w-full hover:shadow-accent" disabled={loading}>
          {loading ? 'Entrando…' : 'Entrar'}
        </Button>
      </form>
    </AuthShell>
  )
}
