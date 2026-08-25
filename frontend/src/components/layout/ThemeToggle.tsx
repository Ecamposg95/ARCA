import { useThemeStore, type ThemeChoice } from '@/stores/themeStore'

const OPTIONS: { key: ThemeChoice; label: string; icon: JSX.Element }[] = [
  {
    key: 'light',
    label: 'Claro',
    icon: (
      <>
        <circle cx="8" cy="8" r="3.2" />
        <path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" />
      </>
    ),
  },
  {
    key: 'system',
    label: 'Sistema',
    icon: (
      <>
        <rect x="1.8" y="2.5" width="12.4" height="8.5" rx="1.2" />
        <path d="M5.5 13.5h5" />
      </>
    ),
  },
  {
    key: 'dark',
    label: 'Oscuro',
    icon: <path d="M13 9.5A5.6 5.6 0 0 1 6.5 3a5.6 5.6 0 1 0 6.5 6.5z" />,
  },
]

export function ThemeToggle() {
  const { choice, setChoice } = useThemeStore()
  return (
    <div className="flex gap-0.5 rounded-lg bg-surface-2 p-0.5" role="group" aria-label="Tema">
      {OPTIONS.map((option) => (
        <button
          key={option.key}
          type="button"
          onClick={() => setChoice(option.key)}
          title={option.label}
          aria-label={option.label}
          aria-pressed={choice === option.key}
          className={`rounded-md p-1.5 transition-colors ${
            choice === option.key ? 'bg-accent text-on-accent' : 'text-muted hover:text-ink'
          }`}
        >
          <svg
            viewBox="0 0 16 16"
            className="h-3.5 w-3.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            aria-hidden
          >
            {option.icon}
          </svg>
        </button>
      ))}
    </div>
  )
}
