/** Selectores y filtros de unidad de negocio y contribuyente.
 *
 *  Sólo aparecen cuando la empresa los definió: una empresa sin sucursales ni
 *  segundo RFC no debe ver un campo que no entiende. */

import { SelectInput } from '@/components/ui/Field'
import { FilterChip } from '@/components/ui/TableTools'
import { useDimensions } from '@/lib/hooks'

export interface DimensionValues {
  business_unit_id: string
  fiscal_entity_id: string
}

export const EMPTY_DIMENSIONS: DimensionValues = { business_unit_id: '', fiscal_entity_id: '' }

/** Los dos selectores del formulario, en una fila. `unitHint` explica la
 *  preselección ("la unidad de la caja elegida"). */
export function DimensionSelects({
  value,
  onChange,
  unitHint,
}: {
  value: DimensionValues
  onChange: (next: DimensionValues) => void
  unitHint?: string
}) {
  const { activeUnits, activeEntities, hasUnits, hasEntities } = useDimensions()
  if (!hasUnits && !hasEntities) return null
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {hasUnits ? (
        <div className="space-y-1">
          <SelectInput
            label="Unidad (opcional)"
            placeholder="Sin unidad"
            options={activeUnits.map((unit) => ({ value: unit.id, label: unit.name }))}
            value={value.business_unit_id}
            onChange={(event) => onChange({ ...value, business_unit_id: event.target.value })}
          />
          {unitHint ? <p className="text-xs text-muted/80">{unitHint}</p> : null}
        </div>
      ) : null}
      {hasEntities ? (
        <SelectInput
          label="Contribuyente (opcional)"
          placeholder="Por asignar"
          options={activeEntities.map((entity) => ({ value: entity.id, label: entity.name }))}
          value={value.fiscal_entity_id}
          onChange={(event) => onChange({ ...value, fiscal_entity_id: event.target.value })}
        />
      ) : null}
    </div>
  )
}

/** Los dos filtros compactos para una barra de herramientas. Todas las
 *  unidades, también las inactivas: su historial sigue existiendo. */
export function DimensionFilterSelects({
  value,
  onChange,
}: {
  value: DimensionValues
  onChange: (next: Partial<DimensionValues>) => void
}) {
  const { units, entities, hasUnits, hasEntities } = useDimensions()
  const selectClass = 'rounded-lg border border-border bg-surface px-2 py-1.5 text-sm'
  return (
    <>
      {hasUnits ? (
        <select
          aria-label="Unidad"
          value={value.business_unit_id}
          onChange={(event) => onChange({ business_unit_id: event.target.value })}
          className={selectClass}
        >
          <option value="">Todas las unidades</option>
          {units.map((unit) => (
            <option key={unit.id} value={unit.id}>
              {unit.name}
              {unit.active ? '' : ' (inactiva)'}
            </option>
          ))}
        </select>
      ) : null}
      {hasEntities ? (
        <select
          aria-label="Contribuyente"
          value={value.fiscal_entity_id}
          onChange={(event) => onChange({ fiscal_entity_id: event.target.value })}
          className={selectClass}
        >
          <option value="">Todos los contribuyentes</option>
          {entities.map((entity) => (
            <option key={entity.id} value={entity.id}>
              {entity.name}
            </option>
          ))}
        </select>
      ) : null}
    </>
  )
}

/** Chips "Unidad: Morelos ×" / "Contribuyente: Liza ×" de lo aplicado. */
export function DimensionChips({
  value,
  onChange,
}: {
  value: DimensionValues
  onChange: (next: Partial<DimensionValues>) => void
}) {
  const { units, entities } = useDimensions()
  const unit = units.find((item) => item.id === value.business_unit_id)
  const entity = entities.find((item) => item.id === value.fiscal_entity_id)
  return (
    <>
      {value.business_unit_id ? (
        <FilterChip
          label={`Unidad: ${unit?.name ?? '…'}`}
          onRemove={() => onChange({ business_unit_id: '' })}
        />
      ) : null}
      {value.fiscal_entity_id ? (
        <FilterChip
          label={`Contribuyente: ${entity?.name ?? '…'}`}
          onRemove={() => onChange({ fiscal_entity_id: '' })}
        />
      ) : null}
    </>
  )
}

/** Querystring de los filtros: nada si no hay nada. */
export function dimensionParams(value: DimensionValues): Record<string, string> {
  return {
    ...(value.business_unit_id ? { business_unit_id: value.business_unit_id } : {}),
    ...(value.fiscal_entity_id ? { fiscal_entity_id: value.fiscal_entity_id } : {}),
  }
}
