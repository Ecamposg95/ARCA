import { useToastStore } from '@/stores/toastStore'

const TONES = {
  info: 'border-border bg-surface text-ink',
  pos: 'border-pos/30 bg-surface text-pos',
  neg: 'border-neg/30 bg-surface text-neg',
}

/** Avisos apilados abajo a la derecha; uno por operación, se cierran solos. */
export function Toasts() {
  const toasts = useToastStore((state) => state.toasts)
  const dismiss = useToastStore((state) => state.dismiss)
  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed inset-x-4 bottom-4 z-[60] flex flex-col items-end gap-2 sm:inset-x-auto sm:right-6">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role="status"
          className={`pointer-events-auto flex max-w-sm items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-card ${TONES[toast.tone]}`}
        >
          <span className="flex-1">{toast.message}</span>
          <button
            type="button"
            onClick={() => dismiss(toast.id)}
            className="text-xs text-muted hover:text-ink"
            aria-label="Cerrar aviso"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  )
}
