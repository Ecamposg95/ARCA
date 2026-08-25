import { SelectInput } from '@/components/ui/Field'
import { formatMoney } from '@/lib/format'
import { splitTotal, TAX_RATES } from '@/lib/taxes'

/** Selector de IVA con el desglose en vivo: el usuario captura el total del
 *  ticket y ve de inmediato en qué se separa. */
export function TaxSelect({
  total,
  rate,
  onRateChange,
}: {
  total: string
  rate: string
  onRateChange: (rate: string) => void
}) {
  const breakdown = splitTotal(total, rate)
  return (
    <div>
      <SelectInput
        label="Impuesto"
        options={TAX_RATES}
        value={rate}
        onChange={(event) => onRateChange(event.target.value)}
      />
      {breakdown.tax > 0 ? (
        <p className="mt-1 text-xs text-muted">
          Subtotal <span className="figures text-ink">{formatMoney(breakdown.subtotal)}</span> · IVA{' '}
          <span className="figures text-ink">{formatMoney(breakdown.tax)}</span>
        </p>
      ) : null}
    </div>
  )
}
