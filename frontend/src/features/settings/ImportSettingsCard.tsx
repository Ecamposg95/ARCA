/** Importación: a dónde cae lo que llega del reporte de ventas de Toronja.
 *
 *  El efectivo va solo a la caja de cada unidad; aquí se eligen el banco de las
 *  transferencias, el procesador de las tarjetas, la categoría de las ventas y
 *  el cliente de los adeudos. */

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput } from '@/components/ui/Field'
import { Card } from '@/components/ui/Table'
import { useAccounts, useCategories, useContacts } from '@/lib/hooks'
import type { ImportSettings } from '@/types/api'

const EMPTY = {
  bank_account_id: '',
  processor_account_id: '',
  receivable_customer_id: '',
  income_category_id: '',
}

export function ImportSettingsCard() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState(EMPTY)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const settings = useQuery({
    queryKey: ['import-settings'],
    queryFn: async () => (await api.get<ImportSettings>('/organizations/current/import-settings')).data,
  })
  const { data: accounts } = useAccounts()
  const { data: categories } = useCategories('INCOME')
  const { data: customers } = useContacts('customers')

  useEffect(() => {
    if (!settings.data) return
    const toronja = settings.data.toronja
    setForm({
      bank_account_id: toronja.bank_account_id ?? '',
      processor_account_id: toronja.processor_account_id ?? '',
      receivable_customer_id: toronja.receivable_customer_id ?? '',
      income_category_id: toronja.income_category_id ?? '',
    })
  }, [settings.data])

  const saveMutation = useMutation({
    mutationFn: async () =>
      (
        await api.patch<ImportSettings>('/organizations/current/import-settings', {
          toronja: {
            bank_account_id: form.bank_account_id || null,
            processor_account_id: form.processor_account_id || null,
            receivable_customer_id: form.receivable_customer_id || null,
            income_category_id: form.income_category_id || null,
          },
        })
      ).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['import-settings'] })
      setError(null)
      setMessage('Cambios guardados.')
    },
    onError: (err) => {
      setMessage(null)
      setError(errorMessage(err))
    },
  })

  // El dinero cobrado sólo puede caer en una cuenta de activo: una tarjeta de crédito no recibe ventas.
  const moneyAccounts = (accounts ?? []).filter((account) => account.active && !account.is_liability)
  const accountOptions = moneyAccounts.map((account) => ({ value: account.id, label: account.name }))
  // Las tarjetas caen en el procesador (NetPay): si la empresa ya tiene uno, sólo se ofrecen procesadores.
  const processors = moneyAccounts.filter((account) => account.type === 'PROCESSOR')
  const processorOptions = processors.length
    ? processors.map((account) => ({ value: account.id, label: account.name }))
    : accountOptions

  return (
    <Card className="mt-6 max-w-lg">
      <h2 className="font-display text-lg font-semibold">Importación</h2>
      <p className="mt-1 text-sm text-muted">
        Cuando subas el reporte de ventas de Toronja, el efectivo cae en la caja de cada unidad. Aquí decides
        dónde caen las tarjetas y las transferencias.
      </p>
      <form
        className="mt-4 space-y-4"
        onSubmit={(event) => {
          event.preventDefault()
          saveMutation.mutate()
        }}
      >
        <SelectInput
          label="Tarjetas (procesador, en tránsito)"
          placeholder="Sin configurar"
          options={processorOptions}
          value={form.processor_account_id}
          onChange={(event) => setForm({ ...form, processor_account_id: event.target.value })}
        />
        <SelectInput
          label="Transferencias (banco)"
          placeholder="Sin configurar"
          options={accountOptions.filter((option) =>
            moneyAccounts.some((account) => account.id === option.value && account.type === 'BANK'),
          )}
          value={form.bank_account_id}
          onChange={(event) => setForm({ ...form, bank_account_id: event.target.value })}
        />
        <SelectInput
          label="Categoría de las ventas"
          placeholder="Ventas (la de siempre)"
          options={(categories ?? []).filter((c) => c.active).map((c) => ({ value: c.id, label: c.name }))}
          value={form.income_category_id}
          onChange={(event) => setForm({ ...form, income_category_id: event.target.value })}
        />
        <SelectInput
          label="Cliente de los adeudos"
          placeholder='Se crea "Pacientes (Toronja)" al importar'
          options={(customers ?? []).map((c) => ({ value: c.id, label: c.name }))}
          value={form.receivable_customer_id}
          onChange={(event) => setForm({ ...form, receivable_customer_id: event.target.value })}
        />
        {message ? <p className="text-sm text-pos">{message}</p> : null}
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <Button type="submit" disabled={saveMutation.isPending || settings.isLoading}>
          Guardar
        </Button>
      </form>
    </Card>
  )
}
