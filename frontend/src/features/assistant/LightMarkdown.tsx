import { Fragment, type ReactNode } from 'react'

/** Markdown ligero (negritas, `código`, listas, párrafos) a elementos React.
 *  El asistente responde con este subconjunto; no hay HTML crudo en ningún punto. */
export function LightMarkdown({ text }: { text: string }) {
  const blocks = splitBlocks(text)
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {blocks.map((block, index) =>
        block.kind === 'list' ? (
          <ul key={index} className="list-disc space-y-0.5 pl-5">
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>{inline(item)}</li>
            ))}
          </ul>
        ) : block.kind === 'ordered' ? (
          <ol key={index} className="list-decimal space-y-0.5 pl-5">
            {block.items.map((item, itemIndex) => (
              <li key={itemIndex}>{inline(item)}</li>
            ))}
          </ol>
        ) : (
          <p key={index}>
            {block.lines.map((line, lineIndex) => (
              <Fragment key={lineIndex}>
                {lineIndex > 0 ? <br /> : null}
                {inline(line)}
              </Fragment>
            ))}
          </p>
        ),
      )}
    </div>
  )
}

type Block =
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'list'; items: string[] }
  | { kind: 'ordered'; items: string[] }

function splitBlocks(text: string): Block[] {
  const blocks: Block[] = []
  let current: Block | null = null
  const flush = () => {
    if (current) blocks.push(current)
    current = null
  }
  for (const raw of text.replace(/\r/g, '').split('\n')) {
    const line = raw.replace(/^#{1,6}\s+/, '').trimEnd()
    if (!line.trim()) {
      flush()
      continue
    }
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/)
    const ordered = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (bullet) {
      if (!current || current.kind !== 'list') {
        flush()
        current = { kind: 'list', items: [] }
      }
      current.items.push(bullet[1])
    } else if (ordered) {
      if (!current || current.kind !== 'ordered') {
        flush()
        current = { kind: 'ordered', items: [] }
      }
      current.items.push(ordered[1])
    } else {
      if (!current || current.kind !== 'paragraph') {
        flush()
        current = { kind: 'paragraph', lines: [] }
      }
      current.lines.push(line.trim())
    }
  }
  flush()
  return blocks
}

/** **negritas** y `código`; el resto es texto tal cual. */
function inline(text: string): ReactNode[] {
  const parts: ReactNode[] = []
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g
  let last = 0
  let match: RegExpExecArray | null
  let key = 0
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const token = match[0]
    if (token.startsWith('**')) {
      parts.push(<strong key={key++}>{token.slice(2, -2)}</strong>)
    } else {
      parts.push(
        <code key={key++} className="figures rounded bg-surface-2 px-1 text-[0.85em]">
          {token.slice(1, -1)}
        </code>,
      )
    }
    last = match.index + token.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts
}
