import { useId } from 'react'
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

const inputClass =
  'w-full rounded border border-border bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/70'

interface FieldProps {
  label: string
  required?: boolean
  hint?: string
  children: (id: string) => ReactNode
}

export function Field({ label, required, hint, children }: FieldProps) {
  const id = useId()
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-muted">
        {label}
        {required ? <span className="text-neg"> *</span> : null}
      </label>
      {children(id)}
      {hint ? <p className="text-xs text-muted/80">{hint}</p> : null}
    </div>
  )
}

export function TextInput({ label, required, hint, ...props }: { label: string; required?: boolean; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <Field label={label} required={required} hint={hint}>
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
