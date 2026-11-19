import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useFeedback } from '@/components/Feedback'
import { wikiApi, type GraphData, type GraphNode, type InsightData } from './wikiApi'
import { EmptyState, PanelHead, Tag, typeLabel } from './ui'

interface Props {
  projectId: string
  onOpenPage: (path: string) => void
  onResearch: (topic: string) => void
  refreshKey: number
}

interface SimNode extends GraphNode {
  x: number
  y: number
  vx: number
  vy: number
}

const GRAPH_LIMIT = 320

const GraphPanel = ({ projectId, onOpenPage, onResearch, refreshKey }: Props) => {
  const { notify, track } = useFeedback()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const nodesRef = useRef<SimNode[]>([])
  const edgesRef = useRef<{ source: string; target: string; weight: number; score: number }[]>([])
  const viewRef = useRef({ k: 1, x: 0, y: 0 })
  const frameRef = useRef(0)
  const dragRef = useRef<{ mode: 'pan' | 'node' | null; id: string; startX: number; startY: number; originX: number; originY: number }>({
    mode: null,
    id: '',
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  })

  const [graph, setGraph] = useState<GraphData | null>(null)
  const [insights, setInsights] = useState<InsightData | null>(null)
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState('')
  const [selected, setSelected] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [graphData, insightData] = await Promise.all([
        wikiApi.graph(projectId, typeFilter || undefined),
        wikiApi.insights(projectId),
      ])
      setGraph(graphData)
      setInsights(insightData)
    } catch {
      setGraph(null)
    } finally {
      setLoading(false)
    }
  }, [projectId, typeFilter])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  const types = useMemo(() => {
    const set = new Set((graph?.nodes || []).map((node) => node.type))
    return [...set]
  }, [graph])

  const nodes = useMemo(() => graph?.nodes || [], [graph])

  // 力导向布局：只做「斥力 + 弹簧 + 向心」，够用且可解释
  useEffect(() => {
    const width = wrapRef.current?.clientWidth || 800
    const height = wrapRef.current?.clientHeight || 520
    const centerX = width / 2
    const centerY = height / 2
    const radius = Math.min(width, height) * 0.34
    const positioned: SimNode[] = nodes.slice(0, GRAPH_LIMIT).map((node, index) => {
      const angle = (index / Math.max(1, nodes.length)) * Math.PI * 2
      const weight = 0.4 + ((index * 37) % 100) / 140
      return {
        ...node,
        x: centerX + Math.cos(angle) * radius * weight,
        y: centerY + Math.sin(angle) * radius * weight,
        vx: 0,
        vy: 0,
      }
    })
    nodesRef.current = positioned
    edgesRef.current = (graph?.edges || []).filter(
      (edge) => positioned.some((node) => node.id === edge.source) && positioned.some((node) => node.id === edge.target),
    )
    viewRef.current = { k: 1, x: 0, y: 0 }
  }, [graph, nodes])
  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return
    const context = canvas.getContext('2d')
    if (!context) return

    let width = 0
    let height = 0
    const resize = () => {
      const rect = wrap.getBoundingClientRect()
      width = Math.max(320, rect.width)
      height = Math.max(320, rect.height)
      const dpr = window.devicePixelRatio || 1
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(wrap)

    let alpha = 1
    let raf = 0
    let hoverId = ''
    let selectedId = ''

    const simulate = () => {
      const list = nodesRef.current
      if (!list.length) return
      const centerX = width / 2
      const centerY = height / 2
      const index = new Map(list.map((node) => [node.id, node]))
      for (let i = 0; i < list.length; i += 1) {
        const a = list[i]
        for (let j = i + 1; j < list.length; j += 1) {
          const b = list[j]
          let dx = a.x - b.x
          let dy = a.y - b.y
          let distance = Math.hypot(dx, dy)
          if (distance < 0.01) {
            dx = (i % 2 ? 1 : -1) * 0.6
            dy = (j % 2 ? 1 : -1) * 0.6
            distance = 0.8
          }
          const repulsion = (1800 / (distance * distance)) * alpha
          const fx = (dx / distance) * repulsion
          const fy = (dy / distance) * repulsion
          a.vx += fx
          a.vy += fy
          b.vx -= fx
          b.vy -= fy
        }
      }
      edgesRef.current.forEach((edge) => {
        const a = index.get(edge.source)
        const b = index.get(edge.target)
        if (!a || !b) return
        const dx = b.x - a.x
        const dy = b.y - a.y
        const distance = Math.max(0.01, Math.hypot(dx, dy))
        const target = 70 + 60 * (1 - edge.weight)
        const force = ((distance - target) / distance) * 0.045 * alpha
        a.vx += dx * force
        a.vy += dy * force
        b.vx -= dx * force
        b.vy -= dy * force
      })
      list.forEach((node) => {
        node.vx += (centerX - node.x) * 0.0016
        node.vy += (centerY - node.y) * 0.0016
        if (node.id !== dragRef.current.id) {
          node.vx *= 0.82
          node.vy *= 0.82
          node.x += node.vx
          node.y += node.vy
        }
      })
      alpha = Math.max(0.05, alpha * 0.994)
    }

    const draw = () => {
      const view = viewRef.current
      context.save()
      context.clearRect(0, 0, width, height)
      context.translate(view.x, view.y)
      context.scale(view.k, view.k)
      const list = nodesRef.current
      const index = new Map(list.map((node) => [node.id, node]))
      const neighbors = new Set<string>()
      const focus = hoverId || selectedId
      if (focus) {
        neighbors.add(focus)
        edgesRef.current.forEach((edge) => {
          if (edge.source === focus) neighbors.add(edge.target)
          if (edge.target === focus) neighbors.add(edge.source)
        })
      }

      edgesRef.current.forEach((edge) => {
        const a = index.get(edge.source)
        const b = index.get(edge.target)
        if (!a || !b) return
        const active = focus && (edge.source === focus || edge.target === focus)
        const dim = focus && !active
        context.beginPath()
        context.moveTo(a.x, a.y)
        context.lineTo(b.x, b.y)
        context.strokeStyle = active
          ? 'rgba(75,78,240,0.65)'
          : dim
            ? 'rgba(148,163,184,0.08)'
            : `rgba(100,116,139,${0.10 + 0.22 * edge.weight})`
        context.lineWidth = active ? 1.6 : 0.8
        context.stroke()
      })

      list.forEach((node) => {
        const dim = focus && !neighbors.has(node.id)
        const radius = 4 + Math.sqrt(node.linkCount + 1) * 2.4
        context.beginPath()
        context.arc(node.x, node.y, node.id === focus ? radius + 3 : radius, 0, Math.PI * 2)
        context.fillStyle = dim ? 'rgba(203,213,225,0.55)' : node.color
        context.globalAlpha = dim ? 0.4 : 1
        context.fill()
        context.globalAlpha = 1
        if (node.id === focus) {
          context.lineWidth = 2
          context.strokeStyle = 'rgba(15,23,42,0.35)'
          context.stroke()
        }
        const showLabel = node.id === focus || node.linkCount >= 4 || view.k > 1.6
        if (showLabel) {
          context.font = `${node.id === focus ? 12 : 10.5}px "PingFang SC", "Microsoft YaHei", system-ui, sans-serif`
          context.fillStyle = dim ? 'rgba(148,163,184,0.6)' : 'rgba(15,23,42,0.82)'
          context.textAlign = 'center'
          const label = node.label.length > 12 ? `${node.label.slice(0, 11)}…` : node.label
          context.fillText(label, node.x, node.y - radius - 6)
        }
      })
      context.restore()
    }

    const tick = () => {
      if (alpha > 0.06 || dragRef.current.mode) simulate()
      draw()
      raf = window.requestAnimationFrame(tick)
    }
    tick()

    const toWorld = (clientX: number, clientY: number) => {
      const rect = canvas.getBoundingClientRect()
      const view = viewRef.current
      return {
        x: (clientX - rect.left - view.x) / view.k,
        y: (clientY - rect.top - view.y) / view.k,
      }
    }

    const findNode = (x: number, y: number): SimNode | null => {
      let best: SimNode | null = null
      let bestDistance = 18
      nodesRef.current.forEach((node) => {
        const radius = 4 + Math.sqrt(node.linkCount + 1) * 2.4
        const distance = Math.hypot(node.x - x, node.y - y)
        if (distance < radius + 6 && distance < bestDistance) {
          bestDistance = distance
          best = node
        }
      })
      return best
    }

    const onPointerMove = (event: PointerEvent) => {
      const point = toWorld(event.clientX, event.clientY)
      if (dragRef.current.mode === 'pan') {
        viewRef.current.x = dragRef.current.originX + (event.clientX - dragRef.current.startX)
        viewRef.current.y = dragRef.current.originY + (event.clientY - dragRef.current.startY)
        return
      }
      if (dragRef.current.mode === 'node') {
        const node = nodesRef.current.find((item) => item.id === dragRef.current.id)
        if (node) {
          node.x = point.x - dragRef.current.originX
          node.y = point.y - dragRef.current.originY
          node.vx = 0
          node.vy = 0
          alpha = Math.max(alpha, 0.35)
        }
        return
      }
      const node = findNode(point.x, point.y)
      hoverId = node?.id || ''
      canvas.style.cursor = node ? 'pointer' : 'grab'
    }

    const onPointerDown = (event: PointerEvent) => {
      const point = toWorld(event.clientX, event.clientY)
      const node = findNode(point.x, point.y)
      if (node) {
        dragRef.current = {
          mode: 'node',
          id: node.id,
          startX: event.clientX,
          startY: event.clientY,
          originX: point.x - node.x,
          originY: point.y - node.y,
        }
        selectedId = node.id
        setSelected(node.id)
      } else {
        dragRef.current = {
          mode: 'pan',
          id: '',
          startX: event.clientX,
          startY: event.clientY,
          originX: viewRef.current.x,
          originY: viewRef.current.y,
        }
        selectedId = ''
        setSelected('')
      }
      canvas.setPointerCapture(event.pointerId)
    }

    const onPointerUp = (event: PointerEvent) => {
      dragRef.current = { mode: null, id: '', startX: 0, startY: 0, originX: 0, originY: 0 }
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId)
    }

    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const view = viewRef.current
      const scale = event.deltaY < 0 ? 1.12 : 0.89
      const next = Math.min(4, Math.max(0.35, view.k * scale))
      const mx = event.clientX - rect.left
      const my = event.clientY - rect.top
      view.x = mx - ((mx - view.x) * next) / view.k
      view.y = my - ((my - view.y) * next) / view.k
      view.k = next
    }

    const onDouble = (event: MouseEvent) => {
      const point = toWorld(event.clientX, event.clientY)
      const node = findNode(point.x, point.y)
      if (node) onOpenPage(node.path)
    }

    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointerup', onPointerUp)
    canvas.addEventListener('wheel', onWheel, { passive: false })
    canvas.addEventListener('dblclick', onDouble)

    return () => {
      window.cancelAnimationFrame(raf)
      observer.disconnect()
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointerup', onPointerUp)
      canvas.removeEventListener('wheel', onWheel)
      canvas.removeEventListener('dblclick', onDouble)
      if (frameRef.current) window.cancelAnimationFrame(frameRef.current)
    }
  }, [graph, onOpenPage])

  const selectedNode = nodes.find((node) => node.id === selected)
  const selectedEdges = (graph?.edges || []).filter((edge) => edge.source === selected || edge.target === selected)
  const selectedNeighbors = selectedEdges
    .map((edge) => (edge.source === selected ? edge.target : edge.source))
    .map((id) => nodes.find((node) => node.id === id))
    .filter((node): node is GraphNode => Boolean(node))

  const startResearch = async (topic: string) => {
    if (!topic.trim()) return
    const result = await track(() => wikiApi.research.start(projectId, topic, { autoIngest: true }), {
      loading: '正在发起深度研究',
      success: '研究任务已启动',
      error: '发起失败',
    })
    if (result) onResearch(topic)
  }

  return (
    <div className="hc-studio__panel hc-studio__panel--graph">
      <PanelHead
        title="知识图谱"
        hint={
          graph
            ? `${graph.stats.pages} 节点 · ${graph.stats.links} 链接 · ${graph.communities.length} 个主题簇 · 4 信号相关性`
            : '读取中…'
        }
        actions={
          <>
            <select
              className="hc-studio__input is-compact"
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
            >
              <option value="">全部类型</option>
              {types.map((type) => (
                <option key={type} value={type}>
                  {typeLabel(type)}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="hc-studio__btn is-ghost"
              onClick={() => {
                nodesRef.current.forEach((node) => {
                  node.vx = (Math.random() - 0.5) * 6
                  node.vy = (Math.random() - 0.5) * 6
                })
                notify('已重新布局', 'success')
              }}
            >
              重排
            </button>
            <button type="button" className="hc-studio__btn" onClick={() => void load()} disabled={loading}>
              刷新
            </button>
          </>
        }
      />

      {!nodes.length && !loading ? (
        <EmptyState title="图谱还是空的" hint="编译至少两份资料后，页面之间的交叉引用会形成图谱。" />
      ) : (
        <div className="hc-studio__graph-wrap">
          <div className="hc-studio__canvas" ref={wrapRef}>
            <canvas ref={canvasRef} />
            <div className="hc-studio__canvas-legend">
              {(graph?.communities || []).slice(0, 8).map((community) => (
                <span key={community.id} className="hc-studio__legend-item">
                  <i style={{ background: community.color }} />
                  {community.label}
                  <em>{community.size}</em>
                  {community.cohesion < 0.15 && community.size >= 3 ? <b title="内聚度偏低">松</b> : null}
                </span>
              ))}
            </div>
            <div className="hc-studio__canvas-tip">滚轮缩放 · 拖拽平移 · 双击打开页面 · 拖动节点可手动布局</div>
          </div>

          <aside className="hc-studio__graph-side">
            {selectedNode ? (
              <div className="hc-studio__card">
                <header className="hc-studio__card-head">
                  <h3>{selectedNode.label}</h3>
                  <Tag tone="indigo">{typeLabel(selectedNode.type)}</Tag>
                </header>
                <div className="hc-studio__row-meta">
                  度 {selectedNode.linkCount} · 社区 {selectedNode.community + 1} · 更新 {selectedNode.updated || '—'}
                </div>
                <div className="hc-studio__chips">
                  {selectedNeighbors.slice(0, 12).map((node) => (
                    <button key={node.id} type="button" className="hc-studio__chip" onClick={() => onOpenPage(node.path)}>
                      {node.label}
                    </button>
                  ))}
                </div>
                <div className="hc-studio__card-actions">
                  <button type="button" className="hc-studio__btn is-ghost" onClick={() => onOpenPage(selectedNode.path)}>
                    打开页面
                  </button>
                  <button
                    type="button"
                    className="hc-studio__btn is-primary"
                    onClick={() => void startResearch(`${selectedNode.label} 的关键争议与最新证据`)}
                  >
                    围绕它研究
                  </button>
                </div>
              </div>
            ) : null}

            <div className="hc-studio__card">
              <header className="hc-studio__card-head">
                <h3>惊人连接</h3>
                <span className="hc-studio__muted">跨社区 / 跨类型 / 外围接枢纽</span>
              </header>
              {(insights?.surprising || []).length === 0 ? (
                <p className="hc-studio__muted hc-studio__card-empty">证据还不够，继续编译资料。</p>
              ) : (
                <ul className="hc-studio__insights">
                  {(insights?.surprising || []).map((item) => (
                    <li key={item.key}>
                      <div className="hc-studio__insight-title">
                        {item.sourceTitle} <span>↔</span> {item.targetTitle}
                      </div>
                      <div className="hc-studio__row-meta">{item.reasons.join(' · ')}</div>
                      <div className="hc-studio__insight-actions">
                        <button
                          type="button"
                          className="hc-studio__link"
                          onClick={() => void startResearch(`${item.sourceTitle} 与 ${item.targetTitle} 的关联机制`)}
                        >
                          深挖关联
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="hc-studio__card">
              <header className="hc-studio__card-head">
                <h3>知识缺口</h3>
                <span className="hc-studio__muted">{insights?.gaps.length || 0} 处</span>
              </header>
              {(insights?.gaps || []).length === 0 ? (
                <p className="hc-studio__muted hc-studio__card-empty">暂未发现明显缺口。</p>
              ) : (
                <ul className="hc-studio__gaps">
                  {(insights?.gaps || []).map((gap, index) => (
                    <li key={`${gap.type}-${index}`}>
                      <div className="hc-studio__gap-head">
                        <Tag tone={gap.type === 'isolated-node' ? 'amber' : gap.type === 'bridge-node' ? 'violet' : 'slate'}>
                          {gap.type === 'isolated-node' ? '孤立' : gap.type === 'bridge-node' ? '桥接' : '松散'}
                        </Tag>
                        <strong>{gap.title}</strong>
                      </div>
                      <p>{gap.description}</p>
                      <div className="hc-studio__insight-actions">
                        <span className="hc-studio__muted">{gap.suggestion}</span>
                        <button type="button" className="hc-studio__link" onClick={() => void startResearch(gap.seed)}>
                          深度研究
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}

export default GraphPanel
