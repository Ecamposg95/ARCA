import axios from 'axios'
import { api, errorMessage } from '@/api/client'

/** Descarga un archivo del API con la sesión del usuario. Un <a href> a secas
 *  no manda el token (vive en localStorage, no en una cookie) y el backend
 *  responde 401. */
export async function downloadFile(
  path: string,
  params: Record<string, string | number>,
  fallbackName: string,
): Promise<void> {
  const response = await api.get<Blob>(path, { params, responseType: 'blob' })
  const disposition = String(response.headers['content-disposition'] ?? '')
  const name = /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? fallbackName
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** Con responseType 'blob' el error del backend también llega como archivo:
 *  hay que leerlo para rescatar el mensaje en español. */
export async function downloadErrorMessage(error: unknown): Promise<string> {
  if (axios.isAxiosError(error) && error.response?.data instanceof Blob) {
    try {
      const detail = JSON.parse(await error.response.data.text()).detail
      if (typeof detail === 'string') return detail
    } catch {
      // no era JSON: cae al mensaje genérico
    }
  }
  return errorMessage(error)
}
