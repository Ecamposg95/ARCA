import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import type { LedgerAccount } from '@/types/api'

/** El número de esta cuenta en el CONTPAQi del contador. Se guarda al salir del
 *  campo o con Enter; vacío quita la equivalencia. */
export function ContpaqiCodeCell({ account }: { account: LedgerAccount }) {
  const queryClient = useQueryClient()
  const saved = account.contpaqi_code ?? ''
  const [value, setValue] = useState(saved)
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: async (next: string) =>
      (
        await api.patch<LedgerAccount>(`/accounting/accounts/${account.id}`, {
          contpaqi_code: next,
        })
      ).data,
    onSuccess: (updated) => {
      setValue(updated.contpaqi_code ?? '')
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function commit() {
    if (value.trim() !== saved) save.mutate(value.trim())
  }

  return (
    <div>
      <input
        aria-label={`Cuenta en CONTPAQi de ${account.code} ${account.name}`}
        className="figures w-40 rounded border border-border bg-surface px-2 py-1 text-sm placeholder:text-muted/50 hover:border-muted/40 disabled:opacity-60"
        placeholder="Sin equivalente"
        value={value}
        maxLength={40}
        disabled={save.isPending}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') setValue(saved)
        }}
      />
      {error ? <p className="mt-1 text-xs text-neg">{error}</p> : null}
    </div>
  )
}
