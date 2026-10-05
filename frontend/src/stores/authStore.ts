import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthResponse, MeResponse, Membership, Organization, User } from '@/types/api'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  /** La empresa activa: la que viaja en X-Organization-ID. */
  organization: Organization | null
  /** Todas las empresas del usuario y su rol en cada una (de /api/me). */
  organizations: Organization[]
  memberships: Membership[]
  isAuthenticated: boolean
  setSession: (auth: AuthResponse) => void
  setCompanies: (me: MeResponse) => void
  setOrganization: (organization: Organization) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      organization: null,
      organizations: [],
      memberships: [],
      isAuthenticated: false,
      setSession: (auth) =>
        set({
          accessToken: auth.access_token,
          refreshToken: auth.refresh_token,
          user: auth.user,
          organization: auth.organization,
          isAuthenticated: true,
        }),
      setCompanies: (me) =>
        set((state) => ({
          organizations: me.organizations,
          memberships: me.memberships,
          // Si la empresa activa ya no es suya (lo sacaron del equipo), se
          // activa otra: quedarse en ella daría 403 en todas las pantallas.
          organization:
            me.organizations.find((company) => company.id === state.organization?.id) ??
            me.organizations[0] ??
            null,
        })),
      setOrganization: (organization) => set({ organization }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          organization: null,
          organizations: [],
          memberships: [],
          isAuthenticated: false,
        }),
    }),
    { name: 'arca-auth' },
  ),
)
