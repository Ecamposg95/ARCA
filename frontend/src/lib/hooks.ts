import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { Category, Contact, FinancialAccount, Page } from '@/types/api'

export function useAccounts() {
  return useQuery({
    queryKey: ['accounts'],
    queryFn: async () => (await api.get<FinancialAccount[]>('/accounts')).data,
  })
}

export function useCategories(kind: 'INCOME' | 'EXPENSE') {
  return useQuery({
    queryKey: ['categories', kind],
    queryFn: async () => (await api.get<Category[]>(`/categories?kind=${kind}`)).data,
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
