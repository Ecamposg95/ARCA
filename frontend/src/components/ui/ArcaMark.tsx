/** Marca ARCA: la "A" con travesaño — arco y balanza. Compartida por login y app. */
export function ArcaMark({ className = 'h-7 w-7' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="hsl(var(--accent))" />
      <path
        d="M9 22 L16 9 L23 22 M12 18 H20"
        stroke="white"
        strokeWidth="2.4"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
