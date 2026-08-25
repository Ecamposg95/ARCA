import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

const styles: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:brightness-110 shadow-card',
  secondary: 'bg-surface border border-border text-ink hover:bg-surface-2',
  ghost: 'text-muted hover:text-ink hover:bg-surface-2',
  danger: 'bg-neg/10 text-neg hover:bg-neg/15',
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

/** Todo botón que no envía formulario lleva type="button" (evita envíos fantasma). */
export function Button({ variant = 'primary', type = 'button', className = '', ...props }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded px-3.5 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none ${styles[variant]} ${className}`}
      {...props}
    />
  )
}
