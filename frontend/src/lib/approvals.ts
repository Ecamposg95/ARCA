/** Autorización por monto, lado cliente. El backend decide; aquí sólo se
 *  reconoce el 202, se avisa y se decide qué avisos enseñar. */

import type { AxiosResponse } from 'axios'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { queryClient } from '@/lib/queryClient'
import { useAuthStore } from '@/stores/authStore'
import { toast } from '@/stores/toastStore'
import type { PendingApproval } from '@/types/api'

export function isPendingApproval(response: AxiosResponse): response is AxiosResponse<PendingApproval> {
  return response.status === 202 && response.data?.pending_approval === true
}

function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? 'quien autoriza'
  return `${names.slice(0, -1).join(', ')} y ${names[names.length - 1]}`
}

/** Toast "Se envió a autorización de ..." y sube el badge de Propuestas. */
export function notifyPendingApproval(body: PendingApproval) {
  toast(`Se envió a autorización de ${joinNames(body.authorizers)}.`)
  void queryClient.invalidateQueries({ queryKey: ['proposals'] })
  void queryClient.invalidateQueries({ queryKey: ['proposals-count'] })
}

/** Si la respuesta fue un 202, avisa y devuelve true; el formulario se cierra igual. */
export function handlePendingApproval(response: AxiosResponse): boolean {
  if (!isPendingApproval(response)) return false
  notifyPendingApproval(response.data)
  return true
}

/** Facultad del usuario en la empresa activa (de /api/me; el dueño siempre). */
export function useCanAuthorize(): boolean {
  return useAuthStore(
    (state) =>
      state.memberships.find((m) => m.organization_id === state.organization?.id)?.can_authorize ??
      false,
  )
}

export interface PendingCount {
  count: number
  approval: number
}

export function usePendingCount() {
  return useQuery({
    queryKey: ['proposals-count'],
    queryFn: async () => (await api.get<PendingCount>('/proposals/pending-count')).data,
    refetchInterval: 60_000,
  })
}
