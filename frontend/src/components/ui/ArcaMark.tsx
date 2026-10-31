/** Marca ONE Finance: la "O" de ONE con su punto — un solo lugar para el dinero. Compartida por login y app. */
export function ArcaMark({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="hsl(var(--accent))" />
      <circle cx="16" cy="16" r="7" stroke="white" strokeWidth="2.4" fill="none" />
      <circle cx="16" cy="16" r="1.8" fill="white" />
    </svg>
  )
}
