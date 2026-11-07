import { useEffect, useRef, useState } from 'react'

/** ¿El sistema pidió menos movimiento? Se consulta al vuelo: puede cambiar con la app abierta. */
export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** La cifra cuenta hacia su valor UNA vez, al montar (≤ 600 ms). Los cambios
 *  posteriores (otro filtro, otra semana) se aplican directo: el movimiento
 *  responde a la llegada del dato, no decora cada actualización. */
export function useCountUp(value: number, durationMs = 600): number {
  const [display, setDisplay] = useState(() => (prefersReducedMotion() ? value : 0))
  const animated = useRef(false)

  useEffect(() => {
    if (animated.current || prefersReducedMotion() || !Number.isFinite(value)) {
      setDisplay(value)
      return
    }
    animated.current = true
    const start = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(value * eased)
      if (progress < 1) frame = requestAnimationFrame(tick)
      else setDisplay(value)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, durationMs])

  return display
}

/** `true` un frame después de montar: las barras arrancan en 0 y crecen con
 *  una transición CSS una sola vez. Con menos movimiento, ya nacen en su tamaño. */
export function useGrowOnce(): boolean {
  const [grown, setGrown] = useState(() => prefersReducedMotion())
  useEffect(() => {
    if (grown) return
    const frame = requestAnimationFrame(() => setGrown(true))
    return () => cancelAnimationFrame(frame)
  }, [grown])
  return grown
}
