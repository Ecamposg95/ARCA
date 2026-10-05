import { QueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (axios.isAxiosError(error)) {
          const status = error.response?.status
          if (status === 401 || status === 403 || status === 404) return false
        }
        return failureCount < 2
      },
    },
  },
})

// La caché es de UNA sesión: quien entra en la misma pestaña no debe ver las
// cifras de quien salió. Cubre salir, entrar, registrarse y la sesión vencida.
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) queryClient.clear()
})
