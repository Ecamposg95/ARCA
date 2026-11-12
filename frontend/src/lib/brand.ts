import { useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import lafeLogoColor from '@/assets/brands/lafe/logo-color.webp'
import lafeLogoBlanco from '@/assets/brands/lafe/logo-blanco.webp'

/** Marca propia de una empresa sobre ONE Finance: su logotipo aquí, sus colores
 *  en `index.css` bajo `[data-brand='<clave>']`. La clave la guarda el backend
 *  (`organizations.brand`, `VALID_BRANDS`). */
export interface Brand {
  name: string
  /** Logotipo para fondo claro y para fondo oscuro. */
  logo: { light: string; dark: string }
}

const BRANDS: Record<string, Brand> = {
  lafe: {
    name: 'Lafe laboratorios',
    logo: { light: lafeLogoColor, dark: lafeLogoBlanco },
  },
}

/** Marca de la empresa activa; null = ONE Finance. Una clave que este front no
 *  conoce se trata como sin marca. */
export function useBrand(): Brand | null {
  const key = useAuthStore((state) => state.organization?.brand ?? null)
  return key ? (BRANDS[key] ?? null) : null
}

/** Pone en <html> la marca de la empresa activa para que los tokens CSS la
 *  lean; al cambiar de empresa o cerrar sesión se quita. */
export function useApplyBrand() {
  const key = useAuthStore((state) => state.organization?.brand ?? null)
  useEffect(() => {
    const root = document.documentElement
    if (key && BRANDS[key]) root.dataset.brand = key
    else delete root.dataset.brand
    return () => {
      delete root.dataset.brand
    }
  }, [key])
}
