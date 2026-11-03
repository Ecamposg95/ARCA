import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { BusinessUnit, Category, Contact, FinancialAccount, FiscalEntity, Page } from '@/types/api'

export function useAccounts() {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: async () => (await api.get<FinancialAccount[]>('/accounts')).data,
  })
}

/** Unidades y contribuyentes de la empresa. Una empresa sin ninguno no ve
 *  selectores, filtros ni columnas: `hasUnits` / `hasEntities` lo deciden. */
export function useDimensions() {
  const units = useQuery({
    queryKey: ['business-units'],
    queryFn: async () => (await api.get<Page<BusinessUnit>>('/business-units?limit=200')).data.items,
  })
  const entities = useQuery({
    queryKey: ['fiscal-entities'],
    queryFn: async () => (await api.get<Page<FiscalEntity>>('/fiscal-entities?limit=200')).data.items,
  })
  const allUnits = units.data ?? []
  const allEntities = entities.data ?? []
  return {
    units: allUnits,
    entities: allEntities,
    // Para asignar: sólo activas. Para filtrar: todas (la historia de una
    // unidad cerrada sigue siendo historia).
    activeUnits: allUnits.filter((unit) => unit.active),
    activeEntities: allEntities.filter((entity) => entity.active),
    hasUnits: allUnits.length > 0,
    hasEntities: allEntities.length > 0,
  }
}

export function useCategories(kind: 'INCOME' | 'EXPENSE') {
  return useQuery({
    queryKey: ['categories', kind],
    queryFn: async () => (await api.get<Category[]>(`/categories?kind=${kind}`)).data,
  })
}

export interface OrgMember {
  id: string
  user_id: string
  name: string
  email: string
  role: string
  is_you: boolean
  can_authorize: boolean
}

/** Quienes registran en la empresa: el filtro "Registró" de las listas. */
export function useMembers() {
  return useQuery({
    queryKey: ['members'],
    queryFn: async () =>
      (await api.get<{ items: OrgMember[] }>('/organizations/current/members')).data.items,
  })
}

export function useContacts(resource: 'customers' | 'vendors') {
  return useQuery({
    queryKey: [resource, 'all'],
    queryFn: async () => (await api.get<Page<Contact>>(`/${resource}?limit=200`)).data.items,
  })
}

/** Cierra un menú al hacer clic fuera o con Escape. */
export function useDismiss(onDismiss: () => void) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onDismiss()
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onDismiss()
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [onDismiss])
  return ref
}
