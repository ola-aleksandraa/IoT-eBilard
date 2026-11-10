#!/usr/bin/env node
// `pnpm dev`: starts both FastAPI backends and the Vite dev server.
//   - website backend      ../back_website   → BACKEND_URL (default http://127.0.0.1:8001)
//   - Raspberry Pi backend ../back_raspberry → PI_URL      (default http://127.0.0.1:8002)
//
// - A backend that already answers on its URL is reused.
// - A URL pointing somewhere else (e.g. PI_URL=http://raspberrypi.local:8002) means "external":
//   nothing is started for it.
// - If uv cannot be found, only Vite starts and the UI falls back to mock data.
// - uv is looked up as $UV, then `uv`, then `mise exec uv -- uv`.
// - CAMERA_SOURCE etc. are passed through to back_raspberry (e.g. CAMERA_SOURCE=../frontend/public/demo/sample-table.png
//   to detect a still image instead of the webcam; relative paths resolve from back_raspberry/).
import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const services = [
  { name: 'website', tag: 'api', dir: resolve(root, '../back_website'), env: 'BACKEND_URL', port: 8001 },
  { name: 'raspberry', tag: 'pi', dir: resolve(root, '../back_raspberry'), env: 'PI_URL', port: 8002 },
].map((s) => {
  const url = process.env[s.env] ?? `http://127.0.0.1:${s.port}`
  const local = new RegExp(`^http://(127\\.0\\.0\\.1|localhost):${s.port}/?$`).test(url)
  return { ...s, url, local }
})

const color = (code, s) => (process.stdout.isTTY ? `\x1b[${code}m${s}\x1b[0m` : s)
const tag = { api: color('36', '[api]'), pi: color('35', '[pi] '), web: color('32', '[web]'), dev: color('33', '[dev]') }
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

async function healthy(url) {
  try {
    const res = await fetch(new URL('/health', url), { signal: AbortSignal.timeout(800) })
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

async function startBackend(svc, uv) {
  if (!svc.local) {
    log(`${svc.env}=${svc.url} – using an external ${svc.name} backend, not starting one`)
    return
  }
  if (await healthy(svc.url)) {
    log(`${svc.name} backend already running at ${svc.url} – reusing it`)
    return
  }
  if (!existsSync(resolve(svc.dir, 'pyproject.toml'))) {
    log(`no ${svc.name} backend found at ${svc.dir} – UI will use mock data`)
    return
  }
  if (!uv) {
    log(`uv not found (set $UV or install uv) – ${svc.name} backend not started`)
    return
  }
  log(`starting ${svc.name} backend on :${svc.port} with: ${uv.join(' ')} run uvicorn … (first run may download Python 3.12)`)
  const args = [
    ...uv.slice(1),
    'run', '--frozen', '--python', '3.12',
    'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(svc.port), '--reload',
  ]
  const child = spawn(uv[0], args, { cwd: svc.dir, env: { ...process.env, PYTHONUNBUFFERED: '1' } })
  children.add(child)
  pipe(child, tag[svc.tag])
  child.on('exit', (code, signal) => {
    children.delete(child)
    if (!shuttingDown) log(`${svc.name} backend exited (${signal ?? code}) – UI keeps running on mock data`)
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

const uv = services.some((s) => s.local) ? findUv() : null
for (const svc of services) await startBackend(svc, uv)
startWeb()
