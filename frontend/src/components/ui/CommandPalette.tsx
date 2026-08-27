/** Paleta de comandos (⌘K / Ctrl+K): a cualquier pantalla o acción en dos teclas.
 *
 *  Sin librería: son dos listas estáticas (navegar y crear) con filtro por
 *  subcadena insensible a acentos. La robustez aquí es que no depende de la
 *  red: si la API está caída, la paleta sigue navegando.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

export interface Command {
  label: string
  hint: string
  to: string
  keywords?: string
}

const NAVIGATE: Command[] = [
  { label: 'Inicio', hint: 'Ir a', to: '/' },
  { label: 'Movimientos', hint: 'Ir a', to: '/movimientos' },
  { label: 'Análisis', hint: 'Ir a', to: '/analisis', keywords: 'terminal graficas series runway efectivo' },
  { label: 'Cuentas de dinero', hint: 'Ir a', to: '/cuentas', keywords: 'bancos tarjetas' },
  { label: 'Patrimonio', hint: 'Ir a', to: '/patrimonio', keywords: 'activos prestamos creditos' },
  { label: 'Ingresos', hint: 'Ir a', to: '/ingresos', keywords: 'ventas' },
  { label: 'Gastos', hint: 'Ir a', to: '/gastos', keywords: 'compras' },
  { label: 'Por cobrar', hint: 'Ir a', to: '/por-cobrar', keywords: 'cxc cartera facturas' },
  { label: 'Por pagar', hint: 'Ir a', to: '/por-pagar', keywords: 'cxp deudas' },
  { label: 'Clientes', hint: 'Ir a', to: '/clientes' },
  { label: 'Proveedores', hint: 'Ir a', to: '/proveedores' },
  { label: 'Proyectos', hint: 'Ir a', to: '/proyectos', keywords: 'rentabilidad margen' },
  { label: 'Reportes', hint: 'Ir a', to: '/reportes', keywords: 'estados financieros' },
  { label: 'Cartera y antigüedad', hint: 'Ir a', to: '/reportes?vista=cartera', keywords: 'dso vencido aging' },
  { label: 'Patrimonio neto', hint: 'Ir a', to: '/reportes?vista=patrimonio', keywords: 'net worth' },
  { label: 'IVA', hint: 'Ir a', to: '/reportes?vista=iva', keywords: 'impuestos sat' },
  { label: 'Contabilidad', hint: 'Ir a', to: '/contabilidad', keywords: 'libro diario polizas' },
  { label: 'Balanza de comprobación', hint: 'Ir a', to: '/contabilidad?vista=balanza', keywords: 'cargos abonos' },
  { label: 'Cierre de periodo', hint: 'Ir a', to: '/contabilidad?vista=periodos', keywords: 'cerrar mes candado' },
  { label: 'Propuestas', hint: 'Ir a', to: '/propuestas', keywords: 'agentes aprobar' },
  { label: 'Configuración', hint: 'Ir a', to: '/configuracion', keywords: 'empresa equipo llaves agentes' },
]

const CREATE: Command[] = [
  { label: 'Nuevo ingreso', hint: 'Crear', to: '/ingresos?nuevo=1', keywords: 'venta cobrar' },
  { label: 'Nuevo gasto', hint: 'Crear', to: '/gastos?nuevo=1', keywords: 'compra pagar' },
  { label: 'Nueva cuenta por cobrar', hint: 'Crear', to: '/por-cobrar?nueva=1', keywords: 'factura credito' },
  { label: 'Nueva cuenta por pagar', hint: 'Crear', to: '/por-pagar?nueva=1' },
  { label: 'Traspaso entre cuentas', hint: 'Crear', to: '/movimientos?transferir=1', keywords: 'transferencia' },
  { label: 'Nuevo cliente', hint: 'Crear', to: '/clientes?nuevo=1' },
  { label: 'Nuevo proveedor', hint: 'Crear', to: '/proveedores?nuevo=1' },
  { label: 'Nueva cuenta de dinero', hint: 'Crear', to: '/cuentas?nueva=1', keywords: 'banco tarjeta' },
  { label: 'Nuevo proyecto', hint: 'Crear', to: '/proyectos?nuevo=1' },
]

function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  const results = useMemo(() => {
    const q = normalize(query.trim())
    const all = [...CREATE, ...NAVIGATE]
    if (!q) return all
    // El título manda: "cier" debe poner "Cierre de periodo" antes que un
    // resultado cuyo keyword apenas contiene la subcadena ("finanCIERos").
    const score = (command: Command) => {
      const label = normalize(command.label)
      if (label.startsWith(q)) return 0
      if (label.includes(q)) return 1
      if (normalize(command.keywords ?? '').includes(q)) return 2
      return -1
    }
    return all
      .map((command) => ({ command, rank: score(command) }))
      .filter((item) => item.rank >= 0)
      .sort((a, b) => a.rank - b.rank)
      .map((item) => item.command)
  }, [query])

  // Al abrir: foco al input y selección al principio.
  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      // El input existe hasta después del render.
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  useEffect(() => setActive(0), [query])

  // La fila activa se mantiene visible al navegar con teclado.
  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [active])

  if (!open) return null

  const run = (command: Command) => {
    onClose()
    navigate(command.to)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/45 px-4 pt-[6vh] sm:pt-[12vh]"
      onMouseDown={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Paleta de comandos"
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'ArrowDown') {
              event.preventDefault()
              setActive((current) => Math.min(current + 1, results.length - 1))
            } else if (event.key === 'ArrowUp') {
              event.preventDefault()
              setActive((current) => Math.max(current - 1, 0))
            } else if (event.key === 'Enter' && results[active]) {
              run(results[active])
            } else if (event.key === 'Escape') {
              onClose()
            }
          }}
          placeholder="Escribe a dónde ir o qué crear…"
          className="w-full border-b border-border bg-transparent px-4 py-3.5 text-sm outline-none placeholder:text-muted"
        />
        <div ref={listRef} className="max-h-80 overflow-y-auto py-1.5">
          {results.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted">
              Nada se llama así. Prueba "gasto", "cierre" o "cartera".
            </p>
          ) : (
            results.map((command, index) => (
              <button
                key={command.to + command.label}
                type="button"
                data-index={index}
                onClick={() => run(command)}
                onMouseEnter={() => setActive(index)}
                className={`flex w-full items-center justify-between px-4 py-2 text-left text-sm ${
                  index === active ? 'bg-accent-soft text-accent' : 'text-ink'
                }`}
              >
                <span>{command.label}</span>
                <span
                  className={`text-[11px] uppercase tracking-wider ${
                    index === active ? 'text-accent/70' : 'text-muted'
                  }`}
                >
                  {command.hint}
                </span>
              </button>
            ))
          )}
        </div>
        <div className="border-t border-border px-4 py-2 text-[11px] text-muted">
          <span className="figures">↑↓</span> moverse · <span className="figures">Enter</span>{' '}
          abrir · <span className="figures">Esc</span> cerrar
        </div>
      </div>
    </div>
  )
}
