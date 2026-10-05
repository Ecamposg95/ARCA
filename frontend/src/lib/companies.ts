import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import { queryClient } from '@/lib/queryClient'
import { useAuthStore } from '@/stores/authStore'
import type { MeResponse, Organization } from '@/types/api'

/** Consultas que son del usuario y no de la empresa activa: sobreviven al cambio. */
const USER_SCOPED = ['me', 'portfolio']

/** Tira todo lo que se pidió para la empresa anterior y vuelve a pedir lo que
 *  esté en pantalla, para que nunca se pinte una cifra de otra empresa. */
function resetCompanyQueries() {
  void queryClient.resetQueries({
    predicate: (query) => !USER_SCOPED.includes(String(query.queryKey[0])),
  })
}

/** Cambia la empresa activa. El orden importa: primero la empresa, para que las
 *  peticiones que dispara el reinicio ya lleven su encabezado. */
export function switchCompany(organization: Organization) {
  useAuthStore.getState().setOrganization(organization)
  resetCompanyQueries()
}

export async function loadCompanies(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>('/me')
  const before = useAuthStore.getState().organization?.id
  useAuthStore.getState().setCompanies(data)
  const after = useAuthStore.getState().organization?.id
  if (before && after !== before) resetCompanyQueries()
  return data
}

export function useCompanies() {
  return useQuery({ queryKey: ['me'], queryFn: loadCompanies })
}

/** Rol del usuario en la empresa activa; null mientras no se conoce. La
 *  autoridad es el backend: esto sólo decide qué navegación se enseña. */
export function useActiveRole(): string | null {
  return useAuthStore(
    (state) =>
      state.memberships.find((m) => m.organization_id === state.organization?.id)?.role ?? null,
  )
}
