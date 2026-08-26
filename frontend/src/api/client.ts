import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

/** Cliente API único. Sin timeout, una request con red degradada nunca resuelve. */
export const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

api.interceptors.request.use((config) => {
  const { accessToken, organization } = useAuthStore.getState()
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  if (organization) {
    config.headers['X-Organization-ID'] = organization.id
  }
  return config
})

/** Cliente aparte: renovar no debe pasar por los interceptores y provocar recursión. */
const plain = axios.create({ baseURL: '/api', timeout: 15000 })

/** Una sola renovación en vuelo; las demás peticiones esperan a esa. */
let renewal: Promise<string> | null = null

function renewSession(): Promise<string> {
  if (renewal) return renewal
  const { refreshToken } = useAuthStore.getState()
  if (!refreshToken) return Promise.reject(new Error('sin refresh token'))

  // /auth/refresh responde con la primera membresía: renovar la sesión no debe
  // mover al usuario de empresa sin que él lo pida.
  const current = useAuthStore.getState().organization

  renewal = plain
    .post('/auth/refresh', { refresh_token: refreshToken })
    .then((response) => {
      useAuthStore.getState().setSession({
        ...response.data,
        organization: current ?? response.data.organization,
      })
      return response.data.access_token as string
    })
    .finally(() => {
      renewal = null
    })
  return renewal
}

function endSession() {
  useAuthStore.getState().logout()
  if (!window.location.pathname.startsWith('/login')) {
    window.location.assign('/login')
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const isAuthCall = typeof original?.url === 'string' && original.url.startsWith('/auth/')

    // El access token dura 12 h y el refresh 30 días: expirar a media captura no
    // debe costarle al usuario lo que estaba escribiendo.
    if (error.response?.status === 401 && original && !original._retried && !isAuthCall) {
      original._retried = true
      try {
        const token = await renewSession()
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` }
        return api(original)
      } catch {
        endSession()
        return Promise.reject(error)
      }
    }

    if (error.response?.status === 401) endSession()
    return Promise.reject(error)
  },
)

/** Pydantic v2 devuelve el detail de 422 como arreglo de objetos; normalízalo SIEMPRE
 * antes de renderizar (React truena con objetos crudos). */
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (typeof item?.msg === 'string' ? item.msg : 'Dato inválido'))
        .join('. ')
    }
    if (error.code === 'ECONNABORTED') return 'La conexión tardó demasiado. Intenta de nuevo.'
  }
  return 'Algo salió mal. Intenta de nuevo.'
}
