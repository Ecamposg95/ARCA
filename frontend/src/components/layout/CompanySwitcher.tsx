import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, ChevronsUpDown } from 'lucide-react'
import { switchCompany } from '@/lib/companies'
import { useDismiss } from '@/lib/hooks'
import { useAuthStore } from '@/stores/authStore'

const ITEM =
  'flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-2'

/** Empresa activa y, para quien lleva varias, el cambio entre ellas. Con una
 *  sola empresa es sólo el nombre: un desplegable de una opción estorba. */
export function CompanySwitcher() {
  const navigate = useNavigate()
  const organization = useAuthStore((state) => state.organization)
  const organizations = useAuthStore((state) => state.organizations)
  const [open, setOpen] = useState(false)
  const ref = useDismiss(() => setOpen(false))

  if (organizations.length < 2) {
    return <div className="min-w-0 flex-1 truncate text-sm font-semibold">{organization?.name}</div>
  }

  const sorted = [...organizations].sort((a, b) => a.name.localeCompare(b.name, 'es'))

  return (
    <div className="relative min-w-0 flex-1" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Cambiar de empresa"
        className="-ml-2 flex max-w-full items-center gap-1.5 rounded-lg px-2 py-1 text-sm font-semibold transition-colors hover:bg-surface-2"
      >
        <span className="truncate">{organization?.name}</span>
        <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted" />
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute left-0 top-10 max-h-80 w-72 overflow-y-auto rounded-xl border border-border bg-surface py-1 shadow-float"
        >
          {sorted.map((company) => (
            <button
              key={company.id}
              type="button"
              role="menuitem"
              className={ITEM}
              onClick={() => {
                setOpen(false)
                if (company.id === organization?.id) return
                switchCompany(company)
                navigate('/')
              }}
            >
              <span className="min-w-0 flex-1 truncate">{company.name}</span>
              {company.id === organization?.id ? (
                <Check className="h-4 w-4 shrink-0 text-accent" />
              ) : null}
            </button>
          ))}
          <button
            type="button"
            role="menuitem"
            className={`${ITEM} border-t border-border text-muted`}
            onClick={() => {
              setOpen(false)
              navigate('/despacho')
            }}
          >
            Ver todas mis empresas
          </button>
        </div>
      ) : null}
    </div>
  )
}
