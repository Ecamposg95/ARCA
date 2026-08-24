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

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.assign('/login')
      }
    }
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
