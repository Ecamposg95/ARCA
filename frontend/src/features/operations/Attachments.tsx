/** Adjuntos de un gasto (HU-05): la foto del ticket o la factura viven con el
 *  movimiento. El backend valida tipo, firma y tamaño; aquí sólo se adelanta
 *  el aviso para no subir 10 MB en vano. */

import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Download, Eye, FileText, Image, Paperclip, Trash2, Upload, X } from 'lucide-react'
import { api, errorMessage } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { downloadErrorMessage } from '@/lib/download'
import { useAuthStore } from '@/stores/authStore'
import type { Attachment, Page } from '@/types/api'

export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
export const MAX_ATTACHMENTS = 10
const EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.pdf', '.xml']
const ACCEPT = [...EXTENSIONS, 'image/*', 'application/pdf', 'application/xml', 'text/xml'].join(',')
const INLINE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf']
const EMPTY_COPY = 'Sube la foto del ticket o la factura (PDF o XML).'

/** Las subidas grandes desde el teléfono tardan más que el timeout general. */
const UPLOAD_TIMEOUT_MS = 120_000

const WRITE_ROLES = ['OWNER', 'ADMIN', 'ACCOUNTANT', 'MEMBER']

export function useCanEditExpenses(): boolean {
  return useAuthStore((state) => {
    const role = state.memberships.find((m) => m.organization_id === state.organization?.id)?.role
    // Sin membresía cargada todavía, el backend decide.
    return role ? WRITE_ROLES.includes(role) : true
  })
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

/** Aviso inmediato en el navegador; null si el archivo puede intentarse. */
export function precheckFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return `${file.name}: sube una foto (JPG, PNG, WEBP o HEIC), un PDF o el XML de la factura.`
  }
  if (file.size > MAX_ATTACHMENT_BYTES) return `${file.name} pesa más de 10 MB.`
  if (file.size === 0) return `${file.name} está vacío.`
  return null
}

export async function uploadAttachment(expenseId: string, file: File): Promise<Attachment> {
  const body = new FormData()
  body.append('file', file)
  const response = await api.post<Attachment>(`/expenses/${expenseId}/attachments`, body, {
    timeout: UPLOAD_TIMEOUT_MS,
  })
  return response.data
}

function formatUploadedAt(iso: string): string {
  return new Date(iso).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
}

function FileIcon({ contentType }: { contentType: string }) {
  const Icon = contentType.startsWith('image/') ? Image : FileText
  return <Icon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
}

/** Zona para soltar o elegir archivos, con botón de cámara en el teléfono. */
function DropZone({
  onFiles,
  disabled,
  compact = false,
}: {
  onFiles: (files: File[]) => void
  disabled?: boolean
  compact?: boolean
}) {
  const picker = useRef<HTMLInputElement>(null)
  const camera = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const take = (list: FileList | null) => {
    const files = Array.from(list ?? [])
    if (files.length > 0) onFiles(files)
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault()
        setDragging(false)
        if (!disabled) take(event.dataTransfer.files)
      }}
      className={`flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 text-center transition-colors ${
        compact ? 'py-3' : 'py-6'
      } ${dragging ? 'border-accent bg-accent-soft/40' : 'border-border bg-surface-2/40'}`}
    >
      <input
        ref={picker}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(event) => {
          take(event.target.files)
          event.target.value = ''
        }}
      />
      {/* capture abre la cámara trasera directo en el teléfono. */}
      <input
        ref={camera}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(event) => {
          take(event.target.files)
          event.target.value = ''
        }}
      />
      {compact ? null : <p className="text-sm text-muted">{EMPTY_COPY}</p>}
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="secondary" className="!px-2.5 !py-1 text-xs" disabled={disabled} onClick={() => picker.current?.click()}>
          <Upload className="h-3.5 w-3.5" /> Elegir archivo
        </Button>
        <Button variant="secondary" className="!px-2.5 !py-1 text-xs sm:hidden" disabled={disabled} onClick={() => camera.current?.click()}>
          <Camera className="h-3.5 w-3.5" /> Tomar foto
        </Button>
      </div>
      <p className="hidden text-[11px] text-muted sm:block">o suéltalos aquí · hasta 10 MB cada uno</p>
    </div>
  )
}

/** Panel de adjuntos de un gasto ya registrado. */
export function AttachmentsPanel({ expenseId }: { expenseId: string }) {
  const queryClient = useQueryClient()
  const canWrite = useCanEditExpenses()
  const [errors, setErrors] = useState<string[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)

  const queryKey = ['attachments', 'expense', expenseId]
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: async () => (await api.get<Page<Attachment>>(`/expenses/${expenseId}/attachments`)).data,
  })
  const items = data?.items ?? []

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey })
    // El clip de la lista de gastos trae el conteo.
    void queryClient.invalidateQueries({ queryKey: ['expense'] })
  }

  const uploadMutation = useMutation({
    mutationFn: async (files: File[]) => {
      const problems: string[] = []
      let room = MAX_ATTACHMENTS - items.length
      for (const file of files) {
        const precheck = precheckFile(file)
        if (precheck) {
          problems.push(precheck)
          continue
        }
        if (room <= 0) {
          problems.push(`${file.name}: ya hay ${MAX_ATTACHMENTS} adjuntos, el máximo.`)
          continue
        }
        try {
          await uploadAttachment(expenseId, file)
          room -= 1
        } catch (err) {
          problems.push(`${file.name}: ${errorMessage(err)}`)
        }
      }
      return problems
    },
    onSuccess: (problems) => {
      setErrors(problems)
      refresh()
    },
  })

  const removeMutation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/attachments/${id}`)
    },
    onSuccess: refresh,
    onError: (err) => setErrors([errorMessage(err)]),
  })

  async function fetchBlob(item: Attachment): Promise<Blob> {
    const response = await api.get<Blob>(`/attachments/${item.id}/download`, {
      responseType: 'blob',
      timeout: UPLOAD_TIMEOUT_MS,
    })
    return response.data
  }

  async function view(item: Attachment) {
    // La pestaña se abre antes de esperar la descarga: si no, el navegador la bloquea.
    const tab = window.open('', '_blank')
    setBusyId(item.id)
    try {
      const url = URL.createObjectURL(await fetchBlob(item))
      if (tab) tab.location.href = url
      else window.location.assign(url)
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      tab?.close()
      setErrors([await downloadErrorMessage(err)])
    } finally {
      setBusyId(null)
    }
  }

  async function download(item: Attachment) {
    setBusyId(item.id)
    try {
      const url = URL.createObjectURL(await fetchBlob(item))
      const link = document.createElement('a')
      link.href = url
      link.download = item.filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setErrors([await downloadErrorMessage(err)])
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="space-y-3">
      {isLoading ? (
        <div className="h-20 animate-pulse rounded-xl bg-surface-2" />
      ) : items.length === 0 ? (
        canWrite ? (
          <DropZone onFiles={(files) => uploadMutation.mutate(files)} disabled={uploadMutation.isPending} />
        ) : (
          <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
            Este gasto todavía no tiene ticket ni factura.
          </p>
        )
      ) : (
        <>
          <ul className="divide-y divide-border rounded-xl border border-border">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 px-3 py-2.5">
                <FileIcon contentType={item.content_type} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={item.filename}>
                    {item.filename}
                  </p>
                  <p className="text-xs text-muted">
                    <span className="figures">{formatBytes(item.size_bytes)}</span> ·{' '}
                    {formatUploadedAt(item.created_at)}
                    {item.uploaded_by_name ? ` · ${item.uploaded_by_name}` : ''}
                  </p>
                </div>
                <div className="flex shrink-0 gap-1">
                  {INLINE_TYPES.includes(item.content_type) ? (
                    <Button
                      variant="ghost"
                      className="!px-2 !py-1"
                      aria-label={`Ver ${item.filename}`}
                      title="Ver"
                      disabled={busyId === item.id}
                      onClick={() => void view(item)}
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    className="!px-2 !py-1"
                    aria-label={`Descargar ${item.filename}`}
                    title="Descargar"
                    disabled={busyId === item.id}
                    onClick={() => void download(item)}
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                  {canWrite ? (
                    <Button
                      variant="ghost"
                      className="!px-2 !py-1 hover:!text-neg"
                      aria-label={`Quitar ${item.filename}`}
                      title="Quitar"
                      disabled={removeMutation.isPending}
                      onClick={() => {
                        if (window.confirm(`¿Quitar "${item.filename}" de este gasto?`)) {
                          removeMutation.mutate(item.id)
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          {canWrite && items.length < MAX_ATTACHMENTS ? (
            <DropZone compact onFiles={(files) => uploadMutation.mutate(files)} disabled={uploadMutation.isPending} />
          ) : null}
        </>
      )}
      {uploadMutation.isPending ? <p className="text-xs text-muted">Subiendo…</p> : null}
      {errors.length > 0 ? (
        <ul className="space-y-0.5 text-sm text-neg">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/** Archivos elegidos al capturar un gasto nuevo: se suben cuando el gasto ya
 *  tiene id (después de guardar). */
export function PendingAttachments({ files, onChange }: { files: File[]; onChange: (files: File[]) => void }) {
  const [errors, setErrors] = useState<string[]>([])

  const add = (incoming: File[]) => {
    const problems: string[] = []
    const next = [...files]
    for (const file of incoming) {
      const precheck = precheckFile(file)
      if (precheck) problems.push(precheck)
      else if (next.length >= MAX_ATTACHMENTS) problems.push(`${file.name}: máximo ${MAX_ATTACHMENTS} adjuntos.`)
      else next.push(file)
    }
    setErrors(problems)
    onChange(next)
  }

  return (
    <div className="space-y-2">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <Paperclip className="h-4 w-4 text-muted" /> Adjuntos (opcional)
      </p>
      {files.length > 0 ? (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {files.map((file, index) => (
            <li key={`${file.name}-${index}`} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              <FileIcon contentType={file.type} />
              <span className="min-w-0 flex-1 truncate">{file.name}</span>
              <span className="figures text-xs text-muted">{formatBytes(file.size)}</span>
              <button
                type="button"
                aria-label={`Quitar ${file.name}`}
                className="rounded p-0.5 text-muted hover:bg-surface-2 hover:text-ink"
                onClick={() => onChange(files.filter((_, position) => position !== index))}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {files.length < MAX_ATTACHMENTS ? <DropZone compact={files.length > 0} onFiles={add} /> : null}
      {errors.length > 0 ? (
        <ul className="space-y-0.5 text-xs text-neg">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
