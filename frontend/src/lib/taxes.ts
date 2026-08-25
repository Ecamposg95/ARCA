/** Desglose de IVA para la vista previa del formulario.
 *
 *  Espeja la fórmula del servidor (app/services/taxes.py), que es la autoridad:
 *  el impuesto se obtiene por diferencia para que subtotal + IVA == total exacto.
 *  Se trabaja en centavos enteros para no arrastrar errores de punto flotante.
 */

export const TAX_RATES = [
  { value: '0.16', label: 'IVA 16%' },
  { value: '0.08', label: 'IVA 8% (frontera)' },
  { value: '0', label: 'Sin IVA / exento' },
]

export interface TaxBreakdown {
  total: number
  subtotal: number
  tax: number
}

export function splitTotal(total: string | number, rate: string | number): TaxBreakdown {
  const totalCents = Math.round(Number(total || 0) * 100)
  const taxRate = Number(rate || 0)
  if (!Number.isFinite(totalCents) || totalCents <= 0 || taxRate <= 0) {
    const value = Number.isFinite(totalCents) ? totalCents / 100 : 0
    return { total: value, subtotal: value, tax: 0 }
  }
  const subtotalCents = Math.round(totalCents / (1 + taxRate))
  return {
    total: totalCents / 100,
    subtotal: subtotalCents / 100,
    tax: (totalCents - subtotalCents) / 100,
  }
}
