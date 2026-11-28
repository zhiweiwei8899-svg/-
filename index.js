/**
 * dsh-dingtalk-workbench — Host half.
 *
 * Registers the `dingtalk_workbench` tool over the checkout's own offline
 * importer (`workbench/collector/ingest.py`). The Python side owns the schema
 * and the normalization rules; this file only resolves an interpreter, runs
 * one command, and turns its single JSON line into a tool result.
 */
import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const PACKAGE_DIR = path.dirname(fileURLToPath(import.meta.url))
const REPO_DIR = process.env.DINGTALK_WORKBENCH_REPO || PACKAGE_DIR
const INGEST_SCRIPT = path.join(REPO_DIR, 'workbench', 'collector', 'ingest.py')
const DEFAULT_DB = path.join(REPO_DIR, 'workbench', 'workbench.db')
const ACTIONS = ['ingest', 'init-db', 'stats', 'search']
const MAX_BUFFER = 16 * 1024 * 1024
const PYTHON_PROBE = [
  'import sys, sqlite3, json',
  'print(json.dumps({"executable": sys.executable, "version": "%d.%d.%d" % sys.version_info[:3]}))',
].join('; ')

let pythonCache = null

/** Ordered interpreter candidates: the explicit override first, then the usual names. */
function pythonCandidates() {
  const list = []
  if (process.env.DINGTALK_WORKBENCH_PYTHON) list.push(process.env.DINGTALK_WORKBENCH_PYTHON)
  if (process.platform === 'win32') {
    list.push('py', 'python3', 'python')
    const home = process.env.USERPROFILE
    if (home) {
      list.push(path.join(home, '.dsh', 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'python.exe'))
    }
  } else {
    list.push('python3', 'python')
  }
  return [...new Set(list)]
}

/** Run one command with bounded output; never rejects. */
function run(command, args, timeout) {
  return new Promise((resolve) => {
    execFile(
      command,
      args,
      {
        timeout,
        maxBuffer: MAX_BUFFER,
        windowsHide: true,
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
          PYTHONUTF8: '1',
          PYTHONUNBUFFERED: '1',
        },
      },
      (error, stdout, stderr) => {
        resolve({
          failed: Boolean(error),
          stdout: stdout || '',
          stderr: stderr || '',
          message: error ? error.message : '',
        })
      },
    )
  })
}

/** First candidate that imports sqlite3, probed once per Host process. */
async function resolvePython() {
  if (pythonCache) return pythonCache
  const tried = []
  for (const candidate of pythonCandidates()) {
    const probe = await run(candidate, ['-c', PYTHON_PROBE], 15_000)
    if (!probe.failed) {
      try {
        const info = JSON.parse(probe.stdout.trim().split('\n').pop())
        pythonCache = { command: candidate, ...info }
        return pythonCache
      } catch {
        // A candidate that prints nothing usable is just another miss.
      }
    }
    tried.push(candidate)
  }
  throw new Error(
    `找不到可用的 Python 3（需要 sqlite3）。已尝试：${tried.join('、')}。` +
      '安装 Python 3 或把环境变量 DINGTALK_WORKBENCH_PYTHON 指到解释器后重试。',
  )
}

/** The script prints exactly one JSON line; pick the last parseable one. */
function parsePayload(text) {
  const lines = text.trim().split('\n').filter(Boolean)
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    try {
      const value = JSON.parse(lines[i])
      if (value && typeof value === 'object') return value
    } catch {
      // Not the payload line.
    }
  }
  return null
}

function resolvePath(input) {
  return path.isAbsolute(input) ? input : path.resolve(REPO_DIR, input)
}

async function executeWorkbench(args) {
  const action = typeof args.action === 'string' ? args.action : ''
  if (!ACTIONS.includes(action)) {
    return { ok: false, error: `action 必须是 ${ACTIONS.join(' / ')}，收到「${action || '(空)'}」。` }
  }
  if (!existsSync(INGEST_SCRIPT)) {
    return {
      ok: false,
      error: `找不到采集脚本 ${INGEST_SCRIPT}。把环境变量 DINGTALK_WORKBENCH_REPO 指向 workbench 检出目录的根。`,
    }
  }

  const dbPath = typeof args.dbPath === 'string' && args.dbPath ? resolvePath(args.dbPath) : DEFAULT_DB
  const cli = ['--action', action, '--db', dbPath]

  if (action === 'ingest') {
    if (typeof args.ndjsonPath !== 'string' || !args.ndjsonPath) {
      return { ok: false, error: 'ingest 需要 ndjsonPath（导出的 NDJSON 文件）。' }
    }
    const ndjsonPath = resolvePath(args.ndjsonPath)
    if (!existsSync(ndjsonPath)) return { ok: false, error: `事件文件不存在：${ndjsonPath}` }
    cli.push('--ndjson', ndjsonPath)
  }

  if (action === 'search') {
    if (typeof args.keyword !== 'string' || !args.keyword) {
      return { ok: false, error: 'search 需要 keyword。' }
    }
    const limit = Math.min(Math.max(Number(args.limit) || 20, 1), 100)
    cli.push('--keyword', args.keyword, '--limit', String(limit))
  }

  const python = await resolvePython()
  const result = await run(python.command, [INGEST_SCRIPT, ...cli], 300_000)
  const payload = parsePayload(result.stdout)
  if (payload) return payload
  return {
    ok: false,
    error: (result.stderr || result.message || '采集脚本没有输出可解析的结果').trim().slice(0, 2000),
  }
}

function render(_args, value) {
  const v = value && typeof value === 'object' ? value : {}
  if (v.ok !== true) {
    return [{ type: 'text', text: `钉钉工作台执行失败：${v.error || '未知错误'}` }]
  }
  if (Array.isArray(v.messages)) {
    if (v.messages.length === 0) {
      return [{ type: 'text', text: `「${v.keyword}」没有命中任何消息。库：${v.db}` }]
    }
    const rows = v.messages.map(
      (m) => `- [${m.sent_at}] ${m.conv_name || m.conv_id} | ${m.sender_name}: ${m.text}`,
    )
    return [
      {
        type: 'text',
        text: `「${v.keyword}」命中 ${v.count} 条：\n${rows.join('\n')}\n库：${v.db}`,
      },
    ]
  }
  if (typeof v.inserted === 'number') {
    return [
      {
        type: 'text',
        text:
          `已入库 ${v.inserted} 条，重复 ${v.duplicated} 条，跳过非消息 ${v.skipped_non_message} 条，坏行 ${v.invalid_lines} 行。\n` +
          `库：${v.db}（会话 ${v.conversations} / 消息 ${v.messages} / 附件 ${v.attachments}，最新 ${v.latest}）`,
      },
    ]
  }
  if (typeof v.conversations === 'number') {
    return [
      {
        type: 'text',
        text: `库：${v.db}，会话 ${v.conversations}，消息 ${v.messages}，附件 ${v.attachments}，最新 ${v.latest}。`,
      },
    ]
  }
  return [{ type: 'text', text: `已初始化数据库：${v.db}` }]
}

const ACTION_LABEL = { ingest: '入库', 'init-db': '初始化', stats: '统计', search: '检索' }

function workbenchTool() {
  return {
    name: 'dingtalk_workbench',
    description:
      '操作 workbench 检出目录里的本地钉钉消息库：把导出的事件 NDJSON 归一化入库，然后报统计、会话，或检索已入库的消息。' +
      '入库按消息幂等，同一份导出重复跑不会产生重复行。需要本机有带 sqlite3 的 Python 3，结果会给出实际使用的数据库文件。',
    parameters: {
      type: 'object',
      properties: {
        action: {
          type: 'string',
          enum: ACTIONS,
          description: 'ingest 导入 NDJSON；init-db 建表或升级结构；stats 报计数；search 检索消息正文。',
        },
        ndjsonPath: {
          type: 'string',
          description: '导出的事件文件，每行一个 JSON 对象。ingest 必填；相对路径按检出目录解析。',
        },
        dbPath: {
          type: 'string',
          description: '要读写的 SQLite 文件。默认是检出目录下的 workbench/workbench.db。',
        },
        keyword: {
          type: 'string',
          description: '检索词，search 必填。三个字符起走全文索引，更短或中文两字走子串扫描。',
        },
        limit: {
          type: 'number',
          description: 'search 返回的条数上限，默认 20，最多 100。',
        },
      },
      required: ['action'],
      additionalProperties: false,
    },
    output: {
      schema: { type: 'object' },
      render,
    },
    execute: async (args) => executeWorkbench(args || {}),
    isConcurrencySafe: () => false,
    presentCall: (args) => {
      const action = args && ACTIONS.includes(args.action) ? args.action : 'stats'
      const target = action === 'search' ? args.keyword : action === 'ingest' ? args.ndjsonPath : ''
      return {
        card: 'generic',
        kind: action === 'ingest' || action === 'init-db' ? 'write' : 'read',
        title: `钉钉工作台 · ${ACTION_LABEL[action]}${target ? `：${target}` : ''}`,
      }
    },
  }
}

export const inject = ['tools']

export function apply(ctx) {
  if (!ctx.tools || typeof ctx.tools.register !== 'function') return
  ctx.effect(() => ctx.tools.register(workbenchTool()), 'dsh-dingtalk-workbench: tool')
}
