/** Unidades y contribuyentes: las dos dimensiones opcionales del libro.
 *
 *  Un negocio con sucursales o con más de un RFC las da de alta aquí y, desde
 *  ese momento, cada operación puede llevarlas y cada reporte filtrarse por
 *  ellas. Nada se borra: una unidad cerrada se desactiva y conserva su historia. */

import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { SelectInput, TextInput } from '@/components/ui/Field'
import { Card } from '@/components/ui/Table'
import { useDimensions } from '@/lib/hooks'
import type { BusinessUnit, FiscalEntity } from '@/types/api'

const KINDS = [
  { value: 'MATRIZ', label: 'Matriz' },
  { value: 'TOMA_MUESTRA', label: 'Toma de muestra' },
  { value: 'UNIDAD_MOVIL', label: 'Unidad móvil' },
  { value: 'CANAL', label: 'Canal' },
  { value: 'OTRA', label: 'Otra' },
]
const KIND_LABELS: Record<string, string> = Object.fromEntries(KINDS.map((kind) => [kind.value, kind.label]))

const EMPTY_UNIT = { name: '', code: '', kind: 'OTRA', opened_on: '', aliases: '' }
const EMPTY_ENTITY = { name: '', tax_id: '', regime: '' }

/** "VNSA, VNSA MOVIL" → ["VNSA", "VNSA MOVIL"]. */
function splitAliases(raw: string): string[] {
  return raw
    .split(',')
    .map((alias) => alias.trim())
    .filter(Boolean)
}

export function DimensionsCard() {
  const { units, entities, hasUnits, hasEntities } = useDimensions()
  return (
    <Card className="mt-6 max-w-lg">
      <h2 className="font-display text-lg font-semibold">Unidades y contribuyentes</h2>
      <p className="mt-1 text-sm text-muted">
        {hasUnits || hasEntities
          ? 'Cada operación puede llevar su unidad y su contribuyente; los reportes se filtran por ellos.'
          : 'Si tu negocio tiene sucursales o más de un contribuyente, dalos de alta aquí para ver tus números por cada uno.'}
      </p>
      <UnitsSection units={units} />
      <EntitiesSection entities={entities} />
    </Card>
  )
}

function UnitsSection({ units }: { units: BusinessUnit[] }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<BusinessUnit | null>(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_UNIT)

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['business-units'] })
  }

  function reset() {
    setOpen(false)
    setEditing(null)
    setError(null)
    setForm(EMPTY_UNIT)
  }

  function startEdit(unit: BusinessUnit) {
    setEditing(unit)
    setOpen(true)
    setError(null)
    setForm({
      name: unit.name,
      code: unit.code,
      kind: unit.kind,
      opened_on: unit.opened_on ?? '',
      aliases: unit.aliases.join(', '),
    })
  }

  const save = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        name: form.name,
        kind: form.kind,
        aliases: splitAliases(form.aliases),
        opened_on: form.opened_on || null,
      }
      if (form.code) payload.code = form.code
      if (editing) await api.patch(`/business-units/${editing.id}`, payload)
      else await api.post('/business-units', payload)
    },
    onSuccess: () => {
      invalidate()
      reset()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggleActive = useMutation({
    mutationFn: async (unit: BusinessUnit) => {
      await api.patch(`/business-units/${unit.id}`, { active: !unit.active })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate()
  }

  return (
    <section className="mt-5">
      <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Unidades</h3>
      {units.length > 0 ? (
        <ul className="mt-2 divide-y divide-border">
          {units.map((unit) => (
            <li key={unit.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <p className={`truncate text-sm font-medium ${unit.active ? '' : 'text-muted line-through'}`}>
                  {unit.name}
                  <span className="figures ml-2 text-xs text-muted">{unit.code}</span>
                </p>
                <p className="text-xs text-muted">
                  {KIND_LABELS[unit.kind] ?? unit.kind}
                  {unit.accounts_count > 0
                    ? ` · ${unit.accounts_count} caja${unit.accounts_count === 1 ? '' : 's'}`
                    : ''}
                </p>
                {unit.aliases.length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {unit.aliases.map((alias) => (
                      <span
                        key={alias}
                        className="rounded-full border border-border bg-surface-2 px-2 py-0.5 text-[11px]"
                      >
                        {alias}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="flex items-center gap-1.5">
                <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => startEdit(unit)}>
                  Editar
                </Button>
                <Button
                  variant="ghost"
                  className="!px-2 !py-1 text-xs"
                  onClick={() => toggleActive.mutate(unit)}
                >
                  {unit.active ? 'Desactivar' : 'Reactivar'}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {open ? (
        <form onSubmit={submit} className="mt-3 space-y-3 border-t border-border pt-4">
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <div className="grid grid-cols-2 gap-3">
            <TextInput
              label="Nombre"
              required
              placeholder="Morelos"
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
            <SelectInput
              label="Tipo"
              options={KINDS}
              value={form.kind}
              onChange={(event) => setForm({ ...form, kind: event.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <TextInput
              label="Código (opcional)"
              placeholder="Se deriva del nombre"
              maxLength={12}
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
            />
            <TextInput
              label="Abrió el (opcional)"
              type="date"
              value={form.opened_on}
              onChange={(event) => setForm({ ...form, opened_on: event.target.value })}
            />
          </div>
          <TextInput
            label="Alias del punto de venta (opcional)"
            placeholder="VILLAS DE NUESTRA SEÑORA, VNSA MOVIL"
            hint="Separados por coma: los nombres con los que Toronja llama a esta unidad."
            value={form.aliases}
            onChange={(event) => setForm({ ...form, aliases: event.target.value })}
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={reset}>
              Cancelar
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {editing ? 'Guardar cambios' : 'Agregar unidad'}
            </Button>
          </div>
        </form>
      ) : (
        <Button variant="secondary" className="mt-3" onClick={() => setOpen(true)}>
          + Agregar unidad
        </Button>
      )}
    </section>
  )
}

function EntitiesSection({ entities }: { entities: FiscalEntity[] }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<FiscalEntity | null>(null)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState(EMPTY_ENTITY)

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['fiscal-entities'] })
  }

  function reset() {
    setOpen(false)
    setEditing(null)
    setError(null)
    setForm(EMPTY_ENTITY)
  }

  function startEdit(entity: FiscalEntity) {
    setEditing(entity)
    setOpen(true)
    setError(null)
    setForm({ name: entity.name, tax_id: entity.tax_id ?? '', regime: entity.regime ?? '' })
  }

  const save = useMutation({
    mutationFn: async () => {
      const payload = { name: form.name, tax_id: form.tax_id || null, regime: form.regime || null }
      if (editing) await api.patch(`/fiscal-entities/${editing.id}`, payload)
      else await api.post('/fiscal-entities', payload)
    },
    onSuccess: () => {
      invalidate()
      reset()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const toggleActive = useMutation({
    mutationFn: async (entity: FiscalEntity) => {
      await api.patch(`/fiscal-entities/${entity.id}`, { active: !entity.active })
    },
    onSuccess: invalidate,
    onError: (err) => window.alert(errorMessage(err)),
  })

  return (
    <section className="mt-5">
      <h3 className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Contribuyentes</h3>
      {entities.length > 0 ? (
        <ul className="mt-2 divide-y divide-border">
          {entities.map((entity) => (
            <li key={entity.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <p className={`truncate text-sm font-medium ${entity.active ? '' : 'text-muted line-through'}`}>
                  {entity.name}
                  {entity.tax_id ? <span className="figures ml-2 text-xs text-muted">{entity.tax_id}</span> : null}
                </p>
                {entity.regime ? <p className="text-xs text-muted">{entity.regime}</p> : null}
              </div>
              <div className="flex items-center gap-1.5">
                <Button variant="ghost" className="!px-2 !py-1 text-xs" onClick={() => startEdit(entity)}>
                  Editar
                </Button>
                <Button
                  variant="ghost"
                  className="!px-2 !py-1 text-xs"
                  onClick={() => toggleActive.mutate(entity)}
                >
                  {entity.active ? 'Desactivar' : 'Reactivar'}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {open ? (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
          className="mt-3 space-y-3 border-t border-border pt-4"
        >
          {error ? <p className="text-sm text-neg">{error}</p> : null}
          <TextInput
            label="Nombre"
            required
            placeholder="Liza"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <TextInput
              label="RFC (opcional)"
              maxLength={13}
              value={form.tax_id}
              onChange={(event) => setForm({ ...form, tax_id: event.target.value.toUpperCase() })}
            />
            <TextInput
              label="Régimen (opcional)"
              placeholder="RESICO"
              value={form.regime}
              onChange={(event) => setForm({ ...form, regime: event.target.value })}
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={reset}>
              Cancelar
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {editing ? 'Guardar cambios' : 'Agregar contribuyente'}
            </Button>
          </div>
        </form>
      ) : (
        <Button variant="secondary" className="mt-3" onClick={() => setOpen(true)}>
          + Agregar contribuyente
        </Button>
      )}
    </section>
  )
}
