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

/** Toast "Se envió a autorización de ..." y sube el badge de Propuestas.
 *  `count` > 1 cuando un lote mandó varias a la vez: un solo aviso, no N. */
export function notifyPendingApproval(body: PendingApproval, count = 1) {
  const who = joinNames(body.authorizers)
  toast(
    count > 1
      ? `${count} operaciones se enviaron a autorización de ${who}.`
      : `Se envió a autorización de ${who}.`,
  )
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

/** Para lotes: reconoce cada 202 sin avisar uno por uno, y al final avisa una vez. */
export function pendingApprovalCollector() {
  let last: PendingApproval | null = null
  let count = 0
  return {
    /** 'pending' si la respuesta fue un 202 de autorización. */
    track(response: AxiosResponse): 'pending' | undefined {
      if (!isPendingApproval(response)) return undefined
      last = response.data
      count += 1
      return 'pending'
    },
    notify() {
      if (last) notifyPendingApproval(last, count)
    },
  }
}
