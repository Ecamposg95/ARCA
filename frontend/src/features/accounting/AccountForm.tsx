/** Alta de una cuenta de detalle: cuelga de una mayor, que fija el tipo. El
 *  código SAT se hereda de la mayor si no se captura. */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Modal } from '@/components/ui/Modal'
import type { LedgerAccount } from '@/types/api'

export function AccountForm({
  open,
  onClose,
  majors,
}: {
  open: boolean
  onClose: () => void
  /** Cuentas mayores (sin padre) de la empresa. */
  majors: LedgerAccount[]
}) {
  const queryClient = useQueryClient()
  // Sin elección explícita se usa la primera mayor; así el formulario funciona
  // aunque el catálogo llegue después de montarlo.
  const [chosenParent, setChosenParent] = useState('')
  const parentId = chosenParent || (majors[0]?.id ?? '')
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [satCode, setSatCode] = useState('')
  const [contpaqiCode, setContpaqiCode] = useState('')
  const [error, setError] = useState<string | null>(null)

  const parent = majors.find((item) => item.id === parentId)

  function reset() {
    setChosenParent('')
    setCode('')
    setName('')
    setSatCode('')
    setContpaqiCode('')
    setError(null)
  }

  const save = useMutation({
    mutationFn: async () =>
      (
        await api.post<LedgerAccount>('/accounting/accounts', {
          parent_id: parentId,
          code: code.trim(),
          name: name.trim(),
          sat_code: satCode.trim() || null,
          contpaqi_code: contpaqiCode.trim() || null,
        })
      ).data,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] })
      reset()
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function close() {
    reset()
    onClose()
  }

  return (
    <Modal title="Nueva cuenta" open={open} onClose={close}>
      <form
        className="space-y-3"
        onSubmit={(event) => {
          event.preventDefault()
          save.mutate()
        }}
      >
        <SelectInput
          label="Cuenta mayor"
          value={parentId}
          options={majors.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` }))}
          onChange={(e) => {
            setChosenParent(e.target.value)
            const major = majors.find((item) => item.id === e.target.value)
            if (major && !code) setCode(major.code.charAt(0))
          }}
          required
        />
        <div className="grid gap-3 sm:grid-cols-[9rem_1fr]">
          <TextInput
            label="Código"
            value={code}
            inputMode="numeric"
            maxLength={10}
            placeholder={parent ? `${parent.code.charAt(0)}210` : '5210'}
            hint={parent ? `Empieza con ${parent.code.charAt(0)}, de 4 a 10 dígitos` : undefined}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            required
          />
          <TextInput
            label="Nombre"
            value={name}
            maxLength={255}
            placeholder="Cuotas patronales IMSS"
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput
            label="Código SAT (opcional)"
            value={satCode}
            list="sat-codes"
            placeholder={parent?.sat_code ? `Hereda ${parent.sat_code}` : 'Sin código'}
            onChange={(e) => setSatCode(e.target.value)}
          />
          <TextInput
            label="Cuenta en CONTPAQi (opcional)"
            value={contpaqiCode}
            maxLength={40}
            placeholder="5210-000-000"
            onChange={(e) => setContpaqiCode(e.target.value)}
          />
        </div>
        {error ? <p className="text-sm text-neg">{error}</p> : null}
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="secondary" onClick={close}>
            Cancelar
          </Button>
          <Button type="submit" disabled={save.isPending || !parentId || code.length < 4 || !name.trim()}>
            {save.isPending ? 'Guardando…' : 'Crear cuenta'}
          </Button>
        </div>
      </form>
    </Modal>
  )
}
