import { useId } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

const inputClass =
  'w-full rounded border border-border bg-surface px-3 py-2.5 text-sm text-ink transition-colors ' +
  'placeholder:text-muted/60 hover:border-muted/40 disabled:cursor-not-allowed disabled:opacity-60'

interface FieldProps {
  label: string
  required?: boolean
  hint?: string
  /** Control secundario alineado a la derecha de la etiqueta (p. ej. "Mostrar" contraseña). */
  action?: ReactNode
  children: (id: string) => ReactNode
}

export function Field({ label, hint, action, children }: FieldProps) {
  const id = useId()
  return (
    <div className="space-y-1">
      {/* Sin asterisco: la convención es que todo es obligatorio salvo que la etiqueta
          diga "(opcional)". Menos ruido, y aria-required sigue informando al lector de pantalla. */}
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="block text-[11px] font-semibold tracking-wide text-muted">
          {label}
        </label>
        {action}
      </div>
      {children(id)}
      {hint ? <p className="text-xs text-muted/80">{hint}</p> : null}
    </div>
  )
}

export function TextInput({
  label,
  required,
  hint,
  action,
  ...props
}: { label: string; required?: boolean; hint?: string; action?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field label={label} required={required} hint={hint} action={action}>
      {(id) => <input id={id} aria-required={required} required={required} className={inputClass} {...props} />}
    </Field>
  )
}

export function SelectInput({
  label,
  required,
  options,
  placeholder,
  ...props
}: {
  label: string
  required?: boolean
  options: { value: string; label: string }[]
  placeholder?: string
} & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <Field label={label} required={required}>
      {(id) => (
        <select id={id} aria-required={required} required={required} className={inputClass} {...props}>
          {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  )
}
