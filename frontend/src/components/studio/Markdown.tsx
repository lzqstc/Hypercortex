/** 轻量 Markdown 渲染器（无第三方依赖）。
 *
 * 支持 wiki 页面里真正会用到的语法：标题、段落、列表、引用、代码块、表格、
 * 加粗/斜体/行内代码/链接/[[wikilink]]/行内公式。
 * 刻意不引入 react-markdown + katex + mermaid：构建体积与首屏速度比语法完备更重要，
 * 公式与图表统一以等宽文本块呈现，保证不崩版。
 */
import { Fragment, type ReactNode } from 'react'

interface Props {
  content: string
  onWikiLink?: (title: string) => void
  onExternal?: (url: string) => void
  compact?: boolean
}

const INLINE_RE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[\[[^\]]+\]\]|\[[^\]]+\]\([^)]+\)|\$[^$\n]+\$)/g

const renderInline = (text: string, props: Props, keyPrefix: string): ReactNode[] => {
  const nodes: ReactNode[] = []
  let lastIndex = 0
  let index = 0
  for (const match of text.matchAll(INLINE_RE)) {
    const raw = match[0]
    const start = match.index ?? 0
    if (start > lastIndex) nodes.push(text.slice(lastIndex, start))
    const key = `${keyPrefix}-${index++}`
    if (raw.startsWith('**')) {
      nodes.push(<strong key={key}>{raw.slice(2, -2)}</strong>)
    } else if (raw.startsWith('`')) {
      nodes.push(
        <code key={key} className="hc-md__code">
          {raw.slice(1, -1)}
        </code>,
      )
    } else if (raw.startsWith('[[')) {
      const label = raw.slice(2, -2).split('|')[0].split('#')[0].trim()
      nodes.push(
        <button
          key={key}
          type="button"
          className="hc-md__wiki"
          onClick={() => props.onWikiLink?.(label)}
          title={`打开：${label}`}
        >
          {label}
        </button>,
      )
    } else if (raw.startsWith('[')) {
      const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(raw)
      if (linkMatch) {
        nodes.push(
          <button
            key={key}
            type="button"
            className="hc-md__link"
            onClick={() => props.onExternal?.(linkMatch[2])}
            title={linkMatch[2]}
          >
            {linkMatch[1]}
          </button>,
        )
      } else {
        nodes.push(raw)
      }
    } else if (raw.startsWith('$')) {
      nodes.push(
        <code key={key} className="hc-md__math">
          {raw.slice(1, -1)}
        </code>,
      )
    } else {
      nodes.push(<em key={key}>{raw.slice(1, -1)}</em>)
    }
    lastIndex = start + raw.length
  }
  if (lastIndex < text.length) nodes.push(text.slice(lastIndex))
  return nodes
}

const splitRow = (line: string) =>
  line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())

export default function Markdown({ content, onWikiLink, onExternal, compact }: Props) {
  const lines = (content || '').replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let index = 0
  let key = 0

  while (index < lines.length) {
    const line = lines[index]

    if (!line.trim()) {
      index += 1
      continue
    }

    if (line.trim().startsWith('```')) {
      const language = line.trim().slice(3).trim()
      const code: string[] = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        code.push(lines[index])
        index += 1
      }
      index += 1
      blocks.push(
        <div key={key++} className="hc-md__pre">
          {language ? <span className="hc-md__pre-lang">{language}</span> : null}
          <pre>{code.join('\n')}</pre>
        </div>,
      )
      continue
    }

    const heading = /^(#{1,4})\s+(.*)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      const text = heading[2].trim()
      const className = `hc-md__h hc-md__h--${level}`
      blocks.push(
        level === 1 ? (
          <h1 key={key++} className={className}>
            {renderInline(text, { content, onWikiLink, onExternal }, `h${key}`)}
          </h1>
        ) : level === 2 ? (
          <h2 key={key++} className={className}>
            {renderInline(text, { content, onWikiLink, onExternal }, `h${key}`)}
          </h2>
        ) : level === 3 ? (
          <h3 key={key++} className={className}>
            {renderInline(text, { content, onWikiLink, onExternal }, `h${key}`)}
          </h3>
        ) : (
          <h4 key={key++} className={className}>
            {renderInline(text, { content, onWikiLink, onExternal }, `h${key}`)}
          </h4>
        ),
      )
      index += 1
      continue
    }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      blocks.push(<hr key={key++} className="hc-md__hr" />)
      index += 1
      continue
    }

    if (line.trimStart().startsWith('>')) {
      const quote: string[] = []
      while (index < lines.length && lines[index].trimStart().startsWith('>')) {
        quote.push(lines[index].trimStart().replace(/^>\s?/, ''))
        index += 1
      }
      blocks.push(
        <blockquote key={key++} className="hc-md__quote">
          {renderInline(quote.join(' '), { content, onWikiLink, onExternal }, `q${key}`)}
        </blockquote>,
      )
      continue
    }

    if (/^\s*\|.+\|\s*$/.test(line) && index + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[index + 1])) {
      const header = splitRow(line)
      index += 2
      const rows: string[][] = []
      while (index < lines.length && /^\s*\|.+\|\s*$/.test(lines[index])) {
        rows.push(splitRow(lines[index]))
        index += 1
      }
      blocks.push(
        <div key={key++} className="hc-md__table-wrap">
          <table className="hc-md__table">
            <thead>
              <tr>
                {header.map((cell, cellIndex) => (
                  <th key={cellIndex}>{renderInline(cell, { content, onWikiLink, onExternal }, `th${cellIndex}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{renderInline(cell, { content, onWikiLink, onExternal }, `td${rowIndex}-${cellIndex}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      )
      continue
    }

    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line)
      const items: string[] = []
      while (index < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*([-*+]|\d+\.)\s+/, ''))
        index += 1
      }
      const children = items.map((item, itemIndex) => (
        <li key={itemIndex}>{renderInline(item, { content, onWikiLink, onExternal }, `li${key}-${itemIndex}`)}</li>
      ))
      blocks.push(
        ordered ? (
          <ol key={key++} className="hc-md__list">
            {children}
          </ol>
        ) : (
          <ul key={key++} className="hc-md__list">
            {children}
          </ul>
        ),
      )
      continue
    }

    const paragraph: string[] = []
    while (
      index < lines.length &&
      lines[index].trim() &&
      !/^(#{1,4}\s|```|>|\s*([-*+]|\d+\.)\s|\s*\|)/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    if (!paragraph.length) {
      paragraph.push(lines[index].trim())
      index += 1
    }
    blocks.push(
      <p key={key++} className="hc-md__p">
        {renderInline(paragraph.join(' '), { content, onWikiLink, onExternal }, `p${key}`)}
      </p>,
    )
  }

  return <div className={`hc-md${compact ? ' hc-md--compact' : ''}`}>{blocks.map((block, blockIndex) => <Fragment key={blockIndex}>{block}</Fragment>)}</div>
}
