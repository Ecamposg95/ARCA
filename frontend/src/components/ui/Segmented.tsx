/** Control segmentado: pestañas y filtros de periodo comparten esta forma. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  size = 'md',
}: {
  options: { key: T; label: string }[]
  value: T
  onChange: (key: T) => void
  size?: 'sm' | 'md'
}) {
  return (
    <div className="flex w-fit gap-1 rounded-lg border border-border bg-surface p-1">
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          onClick={() => onChange(option.key)}
          aria-pressed={value === option.key}
          className={`rounded-md transition-colors ${size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm'} ${
            value === option.key ? 'bg-accent font-medium text-on-accent' : 'text-muted hover:text-ink'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
