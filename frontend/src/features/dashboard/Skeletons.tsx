import type React from 'react'

/** Esqueletos con la forma de cada panel: el ojo ya sabe dónde va a caer cada cosa. */

function Bone({ className, style }: { className: string; style?: React.CSSProperties }) {
  return <div className={`animate-pulse rounded bg-surface-2 ${className}`} style={style} />
}

export function PanelTitleBone() {
  return <Bone className="h-3.5 w-28" />
}

export function MoneySkeleton() {
  return (
    <section className="panel p-4" aria-busy="true" aria-label="Cargando dinero de hoy">
      <PanelTitleBone />
      <Bone className="mt-3 h-10 w-48" />
      <Bone className="mt-2 h-3 w-40" />
      <Bone className="mt-4 h-2 w-full" />
      <div className="mt-3 space-y-2.5">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex items-center gap-2">
            <Bone className="h-2 w-2" />
            <Bone className="h-3 flex-1" />
            <Bone className="h-3 w-16" />
          </div>
        ))}
      </div>
    </section>
  )
}

export function WeekSkeleton() {
  return (
    <section className="panel p-4" aria-busy="true" aria-label="Cargando pagos de la semana">
      <div className="flex justify-between">
        <PanelTitleBone />
        <Bone className="h-3 w-24" />
      </div>
      <div className="mt-4 flex h-[118px] items-end gap-1.5 border-b border-border pb-1">
        {[30, 70, 10, 66, 24, 4, 4].map((height, i) => (
          <Bone key={i} className="flex-1" style={{ height }} />
        ))}
      </div>
      <div className="mt-3 space-y-2.5">
        {[0, 1, 2].map((i) => (
          <Bone key={i} className="h-3 w-full" />
        ))}
      </div>
    </section>
  )
}

export function BranchesSkeleton() {
  return (
    <section className="panel p-4" aria-busy="true" aria-label="Cargando sucursales">
      <div className="flex justify-between">
        <PanelTitleBone />
        <Bone className="h-3 w-36" />
      </div>
      <div className="mt-4 space-y-3">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <Bone className="h-3 w-24" />
            <Bone className="h-1.5 flex-1" />
            <Bone className="h-3 w-16" />
            <Bone className="h-4 w-12" />
            <Bone className="h-5 w-20" />
          </div>
        ))}
      </div>
    </section>
  )
}

export function ChartSkeleton() {
  return (
    <section className="panel p-4" aria-busy="true" aria-label="Cargando ventas por mes">
      <div className="flex justify-between">
        <PanelTitleBone />
        <Bone className="h-3 w-60" />
      </div>
      <Bone className="mt-4 h-[220px] w-full" />
    </section>
  )
}
