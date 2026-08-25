import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ThemeChoice = 'light' | 'dark' | 'system'

interface ThemeState {
  choice: ThemeChoice
  setChoice: (choice: ThemeChoice) => void
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

/** Aplica la clase que leen los tokens CSS. */
export function applyTheme(choice: ThemeChoice) {
  const dark = choice === 'dark' || (choice === 'system' && systemPrefersDark())
  document.documentElement.classList.toggle('dark', dark)
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      choice: 'system',
      setChoice: (choice) => {
        applyTheme(choice)
        set({ choice })
      },
    }),
    {
      name: 'arca-theme',
      onRehydrateStorage: () => (state) => applyTheme(state?.choice ?? 'system'),
    },
  ),
)

/** El sistema puede cambiar de tema mientras la app está abierta. */
export function watchSystemTheme() {
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  media?.addEventListener('change', () => {
    if (useThemeStore.getState().choice === 'system') applyTheme('system')
  })
}
