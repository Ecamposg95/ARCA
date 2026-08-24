import { splitMoney } from '@/lib/format'

/** Cifra estilo ledger: enteros grandes, centavos discretos. La firma visual de ARCA. */
export function Money({
  value,
  size = 'md',
  tone = 'ink',
}: {
  value: string | number | null | undefined
  size?: 'sm' | 'md' | 'lg' | 'xl'
  tone?: 'ink' | 'pos' | 'neg' | 'muted'
}) {
  const { main, cents } = splitMoney(value)
  const sizes = {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-2xl',
    xl: 'text-4xl',
  }
  const centsSizes = {
    sm: 'text-xs',
    md: 'text-xs',
    lg: 'text-sm',
    xl: 'text-lg',
  }
  const tones = {
    ink: 'text-ink',
    pos: 'text-pos',
    neg: 'text-neg',
    muted: 'text-muted',
  }
  return (
    <span className={`figures font-semibold ${sizes[size]} ${tones[tone]}`}>
      {main}
      <span className={`${centsSizes[size]} font-medium opacity-60`}>{cents}</span>
    </span>
  )
}
