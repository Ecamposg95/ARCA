import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { App } from '@/App'
import { queryClient } from '@/lib/queryClient'
import { applyTheme, useThemeStore, watchSystemTheme } from '@/stores/themeStore'
import '@/index.css'

// Antes del primer render para evitar el parpadeo claro→oscuro.
applyTheme(useThemeStore.getState().choice)
watchSystemTheme()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
