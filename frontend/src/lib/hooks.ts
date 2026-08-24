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
