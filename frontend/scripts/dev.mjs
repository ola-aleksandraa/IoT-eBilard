#!/usr/bin/env node
// `pnpm dev`: starts the website FastAPI backend (../back_website, port 8001) and the Vite dev server.
//
// - If a backend already answers on BACKEND_URL (default http://127.0.0.1:8001), it is reused.
// - If BACKEND_URL points somewhere else, or uv cannot be found, only Vite starts and the
//   UI falls back to mock data.
// - uv is looked up as $UV, then `uv`, then `mise exec uv -- uv`.
import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const backendDir = resolve(root, '../back_website')
const backendUrl = process.env.BACKEND_URL ?? 'http://127.0.0.1:8001'
const isLocalDefault = !process.env.BACKEND_URL || /^http:\/\/(127\.0\.0\.1|localhost):8001\/?$/.test(backendUrl)

const color = (code, s) => (process.stdout.isTTY ? `\x1b[${code}m${s}\x1b[0m` : s)
const tag = { api: color('36', '[api]'), web: color('32', '[web]'), dev: color('33', '[dev]') }
const log = (msg) => console.log(`${tag.dev} ${msg}`)

function pipe(child, prefix) {
  for (const stream of [child.stdout, child.stderr]) {
    let buf = ''
    stream.on('data', (chunk) => {
      buf += chunk
      const lines = buf.split('\n')
      buf = lines.pop()
      for (const line of lines) console.log(`${prefix} ${line}`)
    })
  }
}

async function backendHealthy() {
  try {
    const res = await fetch(new URL('/health', backendUrl), { signal: AbortSignal.timeout(800) })
    return res.ok
  } catch {
    return false
  }
}

function findUv() {
  const candidates = [
    process.env.UV ? [process.env.UV] : null,
    ['uv'],
    ['mise', 'exec', 'uv', '--', 'uv'],
  ].filter(Boolean)
  for (const cmd of candidates) {
    const probe = spawnSync(cmd[0], [...cmd.slice(1), '--version'], { encoding: 'utf8' })
    if (probe.status === 0) return cmd
  }
  return null
}

const children = new Set()
let shuttingDown = false

function shutdown(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const child of children) child.kill('SIGTERM')
  setTimeout(() => process.exit(code), 1500).unref()
}
process.on('SIGINT', () => shutdown(0))
process.on('SIGTERM', () => shutdown(0))

async function startBackend() {
  if (!isLocalDefault) {
    log(`BACKEND_URL=${backendUrl} – using an external backend, not starting one`)
    return
  }
  if (await backendHealthy()) {
    log(`backend already running at ${backendUrl} – reusing it`)
    return
  }
  if (!existsSync(resolve(backendDir, 'pyproject.toml'))) {
    log(`no backend found at ${backendDir} – UI will use mock data`)
    return
  }
  const uv = findUv()
  if (!uv) {
    log('uv not found (set $UV or install uv) – UI will use mock data')
    return
  }
  log(`starting backend with: ${uv.join(' ')} run uvicorn … (first run may download Python 3.12)`)
  const args = [
    ...uv.slice(1),
    'run', '--frozen', '--python', '3.12',
    'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001', '--reload',
  ]
  const api = spawn(uv[0], args, { cwd: backendDir, env: { ...process.env, PYTHONUNBUFFERED: '1' } })
  children.add(api)
  pipe(api, tag.api)
  api.on('exit', (code, signal) => {
    children.delete(api)
    if (!shuttingDown) log(`backend exited (${signal ?? code}) – UI keeps running on mock data`)
  })
}

function startWeb() {
  const viteBin = resolve(root, 'node_modules/vite/bin/vite.js')
  const web = spawn(process.execPath, [viteBin, ...process.argv.slice(2)], { cwd: root, env: process.env })
  children.add(web)
  pipe(web, tag.web)
  web.on('exit', (code) => {
    children.delete(web)
    shutdown(code ?? 0)
  })
}

await startBackend()
startWeb()
