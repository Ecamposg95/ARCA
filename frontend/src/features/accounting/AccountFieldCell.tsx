import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import type { LedgerAccount } from '@/types/api'

type Field = 'contpaqi_code' | 'sat_code'

/** Un dato editable de una cuenta del catálogo (equivalente en CONTPAQi o código
 *  agrupador del SAT). Se guarda al salir del campo o con Enter; vacío lo quita. */
export function AccountFieldCell({
  account,
  field,
  placeholder,
  list,
  caption,
}: {
  account: LedgerAccount
  field: Field
  placeholder: string
  /** id de un <datalist> con las opciones válidas */
  list?: string
  /** texto bajo el campo (p. ej. el nombre del código elegido) */
  caption?: string
}) {
  const queryClient = useQueryClient()
  const saved = account[field] ?? ''
  const [value, setValue] = useState(saved)
  const [error, setError] = useState<string | null>(null)
  const editing = useRef(false)

  // Si la lista se vuelve a pedir (otra sesión guardó algo), el campo sigue a
  // lo guardado mientras nadie lo esté editando: así no se pisa un dato ajeno.
  useEffect(() => {
    if (!editing.current) setValue(saved)
  }, [saved])

  const save = useMutation({
    mutationFn: async (next: string) =>
      (await api.patch<LedgerAccount>(`/accounting/accounts/${account.id}`, { [field]: next })).data,
    onSuccess: (updated) => {
      setValue(updated[field] ?? '')
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['accounting', 'accounts'] })
    },
    onError: (err) => setError(errorMessage(err)),
  })

  function commit() {
    editing.current = false
    if (value.trim() !== saved) save.mutate(value.trim())
  }

  return (
    <div>
      <input
        aria-label={`${placeholder} de ${account.code} ${account.name}`}
        list={list}
        className="figures w-40 rounded border border-border bg-surface px-2 py-1 text-sm placeholder:text-muted/50 hover:border-muted/40 disabled:opacity-60"
        placeholder={placeholder}
        value={value}
        maxLength={40}
        disabled={save.isPending}
        onFocus={() => {
          editing.current = true
        }}
        onChange={(event) => setValue(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
          if (event.key === 'Escape') {
            setValue(saved)
            setError(null)
          }
        }}
      />
      {error ? (
        <p className="mt-1 text-xs text-neg">{error}</p>
      ) : caption ? (
        <p className="mt-0.5 max-w-[10rem] truncate text-[11px] text-muted" title={caption}>
          {caption}
        </p>
      ) : null}
    </div>
  )
}
