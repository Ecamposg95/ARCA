import { create } from 'zustand'

export interface Toast {
  id: number
  message: string
  tone: 'info' | 'pos' | 'neg'
}

interface ToastState {
  toasts: Toast[]
  push: (message: string, tone?: Toast['tone']) => void
  dismiss: (id: number) => void
}

let nextId = 1

/** Avisos breves que no interrumpen: "se envió a autorización", etc.
 *  Se van solos a los 6 s; el usuario puede cerrarlos antes. */
export const useToastStore = create<ToastState>()((set) => ({
  toasts: [],
  push: (message, tone = 'info') => {
    const id = nextId++
    set((state) => ({ toasts: [...state.toasts, { id, message, tone }] }))
    window.setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }))
    }, 6000)
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) })),
}))

export function toast(message: string, tone: Toast['tone'] = 'info') {
  useToastStore.getState().push(message, tone)
}
