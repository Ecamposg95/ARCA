import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AuthResponse, Organization, User } from '@/types/api'

interface AuthState {
  accessToken: string | null
  refreshToken: string | null
  user: User | null
  organization: Organization | null
  isAuthenticated: boolean
  setSession: (auth: AuthResponse) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      organization: null,
      isAuthenticated: false,
      setSession: (auth) =>
        set({
          accessToken: auth.access_token,
          refreshToken: auth.refresh_token,
          user: auth.user,
          organization: auth.organization,
          isAuthenticated: true,
        }),
      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          organization: null,
          isAuthenticated: false,
        }),
    }),
    { name: 'arca-auth' },
  ),
)
