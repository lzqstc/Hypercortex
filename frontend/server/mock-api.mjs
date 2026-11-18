import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'

const PORT = Number(process.env.API_PORT || 3001)
const LATENCY = Number(process.env.API_LATENCY || 320)

const state = {
  projects: [],
  uploads: [],
  conversations: [],
  researches: [],
  notifications: [
    { id: randomUUID(), title: '欢迎使用 HyperCortex', detail: '示例数据已切换为空白工作区', read: false },
  ],
  settings: {
    autoSync: true,
    deepSearch: true,
    citations: false,
  },
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const send = (res, status, payload) => {
  const body = JSON.stringify(payload)
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  })
  res.end(body)
}

const readBody = (req) =>
  new Promise((resolve, reject) => {
    let body = ''
    req.on('data', (chunk) => {
      body += chunk
      if (body.length > 2_000_000) {
        reject(new Error('请求体过大'))
        req.destroy()
      }
    })
    req.on('end', () => {
      if (!body) return resolve({})
      try {
        resolve(JSON.parse(body))
      } catch {
        reject(new Error('请求体不是合法 JSON'))
      }
    })
    req.on('error', reject)
  })

const normalizeFiles = (files) =>
  (Array.isArray(files) ? files : []).map((file) => ({
    id: randomUUID(),
    name: String(file?.name || '未命名文件'),
    size: Number(file?.size || 0),
    status: 'processing',
    progress: 0,
    createdAt: new Date().toISOString(),
  }))

const server = createServer(async (req, res) => {
  const startedAt = Date.now()
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`)
  const path = url.pathname

  res.on('finish', () => {
    console.log(`${req.method} ${path} ${res.statusCode} ${Date.now() - startedAt}ms`)
  })

  try {
    if (req.method === 'OPTIONS') {
      res.writeHead(204, {
        'access-control-allow-origin': '*',
        'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS',
        'access-control-allow-headers': 'content-type',
      })
      res.end()
      return
    }

    if (path === '/api/health' && req.method === 'GET') {
      return send(res, 200, { ok: true, service: 'hypercortex-mock-api', time: new Date().toISOString() })
    }

    if (path === '/api/bootstrap' && req.method === 'GET') {
      await sleep(LATENCY)
      return send(res, 200, {
        projects: state.projects,
        uploads: state.uploads,
        conversations: state.conversations,
        researches: state.researches,
        notifications: state.notifications,
        settings: state.settings,
      })
    }

    if (path === '/api/projects' && req.method === 'GET') {
      await sleep(LATENCY)
      return send(res, 200, { items: state.projects })
    }

    if (path === '/api/projects' && req.method === 'POST') {
      const body = await readBody(req)
      const name = String(body.name || '').trim()
      if (!name) return send(res, 400, { error: '项目名称不能为空' })

      await sleep(LATENCY)
      const project = {
        id: randomUUID(),
        name,
        template: String(body.template || '产品知识库'),
        team: String(body.team || '产品与体验中心'),
        visibility: String(body.visibility || '团队可见'),
        createdAt: new Date().toISOString(),
      }
      state.projects.unshift(project)
      state.notifications.unshift({
        id: randomUUID(),
        title: '项目创建成功',
        detail: `${project.name} 已创建，可以开始上传资料`,
        read: false,
      })
      return send(res, 201, { item: project })
    }

    if (path === '/api/uploads' && req.method === 'GET') {
      await sleep(LATENCY)
      return send(res, 200, { items: state.uploads })
    }

    if (path === '/api/uploads' && req.method === 'POST') {
      const body = await readBody(req)
      const files = normalizeFiles(body.files)
      if (!files.length) return send(res, 400, { error: '请选择至少一个文件' })

      await sleep(LATENCY)
      const job = {
        id: randomUUID(),
        files,
        total: files.length,
        status: 'processing',
        createdAt: new Date().toISOString(),
      }
      state.uploads.unshift(job)
      state.notifications.unshift({
        id: randomUUID(),
        title: '资料已提交解析',
        detail: `${job.total} 个文件已进入解析队列`,
        read: false,
      })
      return send(res, 202, { item: job })
    }

    if (path === '/api/chat' && req.method === 'POST') {
      const body = await readBody(req)
      const question = String(body.question || '').trim()
      if (!question) return send(res, 400, { error: '请输入问题' })

      await sleep(LATENCY + 180)
      const conversation = {
        id: randomUUID(),
        question,
        answer:
          '这是演示回答。真实回答将在接入检索服务后生成，并会附带来源片段、页码与可信度。',
        sources: [
          { id: randomUUID(), title: '演示资料片段 A', score: 0.92 },
          { id: randomUUID(), title: '演示资料片段 B', score: 0.86 },
        ],
        createdAt: new Date().toISOString(),
      }
      state.conversations.unshift(conversation)
      return send(res, 200, { item: conversation })
    }

    if (path === '/api/research' && req.method === 'GET') {
      await sleep(LATENCY)
      return send(res, 200, { items: state.researches })
    }

    if (path === '/api/research' && req.method === 'POST') {
      const body = await readBody(req)
      const topic = String(body.topic || '').trim()
      if (!topic) return send(res, 400, { error: '请输入研究主题' })

      await sleep(LATENCY + 120)
      const research = {
        id: randomUUID(),
        topic,
        status: 'running',
        steps: ['拆解研究主题', '检索并聚类证据', '交叉验证矛盾点', '生成结构化结论'],
        createdAt: new Date().toISOString(),
      }
      state.researches.unshift(research)
      state.notifications.unshift({
        id: randomUUID(),
        title: '研究任务已启动',
        detail: topic,
        read: false,
      })
      return send(res, 202, { item: research })
    }

    if (path === '/api/settings' && req.method === 'PATCH') {
      const body = await readBody(req)
      await sleep(Math.round(LATENCY / 2))
      state.settings = { ...state.settings, ...body }
      return send(res, 200, { item: state.settings })
    }

    if (path === '/api/notifications' && req.method === 'GET') {
      await sleep(Math.round(LATENCY / 2))
      return send(res, 200, { items: state.notifications })
    }

    return send(res, 404, { error: `接口不存在：${path}` })
  } catch (error) {
    return send(res, 500, { error: error instanceof Error ? error.message : String(error) })
  }
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`HyperCortex mock API listening on http://localhost:${PORT}`)
})
