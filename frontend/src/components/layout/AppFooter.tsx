import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

interface Health {
  status: string
  service: string
  environment: string
  version: string
}

/** Pie discreto: identidad, versión y —sólo fuera de producción— el entorno,
 *  para no confundir un ambiente de prueba con el real. */
export function AppFooter() {
  const { data } = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await api.get<Health>('/health')).data,
    staleTime: 10 * 60 * 1000,
    retry: false,
  })

  return (
    <footer className="shrink-0 border-t border-border bg-surface px-6 py-3 lg:px-10">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 text-xs text-muted">
        <span>
          <span className="font-semibold text-ink">ARCA</span> · Financial Operating System by Atlas
          Tech
        </span>
        <span className="figures flex items-center gap-3">
          {data?.environment && data.environment !== 'production' ? (
            <span className="rounded bg-warn/15 px-1.5 py-0.5 font-medium uppercase text-warn">
              {data.environment}
            </span>
          ) : null}
          {data?.version ? <span>v{data.version}</span> : null}
        </span>
      </div>
    </footer>
  )
}
