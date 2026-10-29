/**
 * multi-model-router — Desktop UI
 *
 * Provides:
 *  1. Sidebar page "Model Router" (Add & Manage unlimited Antigravity & Claude accounts, individual proxy controls, delete)
 *  2. Composer action "Auto" toggle with dropup menu (select default model, reorder priority list)
 */
import {
  Button,
  Codicon,
  COMPOSER_AREAS,
  host,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  Switch,
  Tip,
  useQuery,
  useQueryClient
} from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'multi-model-router'
const KEY_STATUS = [ID, 'status']
const KEY_AUTO = [ID, 'autoswitch']
const KEY_MODELS = [ID, 'models']
let CTX = null

const api = (path, opts) => CTX.rest(path, opts)

function h(type, props, ...kids) {
  const flat = kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false)
  const p = { ...(props || {}) }
  if (flat.length === 1) {
    p.children = flat[0]
    return jsx(type, p)
  }
  if (flat.length > 1) {
    p.children = flat
    return jsxs(type, p)
  }
  return jsx(type, p)
}

const CSS = `
.mmr-page{height:100%;overflow-y:auto;padding:24px;box-sizing:border-box}
.mmr-wrap{max-width:820px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
.mmr-h1{font-size:1.25rem;font-weight:600;color:var(--ui-text-primary);display:flex;align-items:center;gap:8px}
.mmr-card{border:1px solid var(--ui-stroke-secondary);border-radius:10px;padding:16px;display:flex;flex-direction:column;gap:12px;background:var(--ui-bg-card,transparent)}
.mmr-title{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--ui-text-quaternary);font-weight:600}
.mmr-row{display:flex;align-items:center;gap:10px}
.mmr-wrapRow{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.mmr-grow{flex:1;min-width:0}
.mmr-dot{width:8px;height:8px;border-radius:50%;flex:none;display:inline-block}
.mmr-text{font-size:.84rem;color:var(--ui-text-primary)}
.mmr-strong{font-size:.92rem;font-weight:600;color:var(--ui-text-primary)}
.mmr-muted{font-size:.75rem;color:var(--ui-text-tertiary);line-height:1.4}
.mmr-faint{font-size:.7rem;color:var(--ui-text-quaternary)}
.mmr-trunc{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mmr-acc{border-top:1px solid var(--ui-stroke-tertiary);padding-top:10px}
.mmr-acc:first-of-type{border-top:0;padding-top:0}
.mmr-badge{font-size:.65rem;padding:2px 8px;border-radius:999px;border:1px solid var(--ui-stroke-secondary);color:var(--ui-text-tertiary);flex:none}
.mmr-pill{display:inline-flex;align-items:center;gap:6px;height:var(--composer-control-size,28px);padding:0 8px;border-radius:6px;font-size:.75rem;color:var(--ui-text-tertiary);background:transparent;border:0;cursor:pointer;white-space:nowrap}
.mmr-pill:hover,.mmr-pill[data-state=open]{background:var(--chrome-action-hover);color:var(--foreground)}
.mmr-pill.on{color:var(--ui-accent);font-weight:500}
.mmr-pop{width:100%;max-width:100%;box-sizing:border-box;display:flex;flex-direction:column;gap:12px;padding:12px;overflow:hidden}
.mmr-pop *{box-sizing:border-box}
.mmr-sec{display:flex;flex-direction:column;gap:6px;min-width:0}
.mmr-sechead{display:flex;align-items:center;justify-content:space-between}
.mmr-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:7px;border:1px solid var(--ui-stroke-tertiary);min-width:0;max-width:100%;overflow:hidden}
.mmr-item.active{border-color:var(--ui-accent)}
.mmr-item.btn{cursor:pointer;background:transparent;width:100%;text-align:left;color:inherit;font:inherit}
.mmr-item.btn:hover{background:var(--chrome-action-hover)}
.mmr-idx{width:16px;text-align:center;font-size:.68rem;color:var(--ui-text-quaternary);flex:none}
.mmr-list{max-height:16rem;overflow-y:auto;overflow-x:hidden;display:flex;flex-direction:column;gap:4px;min-width:0}
.mmr-ib{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:5px;border:0;background:transparent;color:var(--ui-text-tertiary);cursor:pointer;flex:none}
.mmr-ib:hover{background:var(--chrome-action-hover);color:var(--ui-text-primary)}
.mmr-ib[disabled]{opacity:.35;cursor:default;pointer-events:none}
.mmr-ib.danger:hover{color:var(--ui-red)}
.mmr-loginbox{display:flex;flex-direction:column;gap:8px;padding:10px;background:var(--ui-bg-quaternary,rgba(255,255,255,0.03));border:1px dashed var(--ui-stroke-secondary);border-radius:8px;margin-top:6px}
`

function injectCss() {
  const old = document.getElementById('mmr-css')
  if (old) old.remove()
  const el = document.createElement('style')
  el.id = 'mmr-css'
  el.textContent = CSS
  document.head.appendChild(el)
}

const GREEN = 'var(--ui-green)'
const YELLOW = 'var(--ui-yellow)'
const RED = 'var(--ui-red)'
const GREY = 'var(--ui-text-quaternary)'

const Dot = ({ color, title }) => h('span', { className: 'mmr-dot', style: { background: color }, title })

const IconBtn = ({ name, label, onClick, disabled, danger }) =>
  h(Tip, { label }, h('button', { type: 'button', className: `mmr-ib${danger ? ' danger' : ''}`, disabled, onClick, 'aria-label': label }, h(Codicon, { name })))

function useStatus() {
  return useQuery({
    queryKey: KEY_STATUS,
    queryFn: () => api('/status?ensure=1', { timeoutMs: 30000 }),
    refetchInterval: 15000,
    staleTime: 5000
  })
}

function useAuto() {
  return useQuery({
    queryKey: KEY_AUTO,
    queryFn: () => api('/autoswitch', { timeoutMs: 30000 }),
    refetchInterval: 30000,
    staleTime: 5000
  })
}

function useModelCatalog() {
  return useQuery({
    queryKey: KEY_MODELS,
    staleTime: 60000,
    queryFn: async () => {
      const res = await host.request('model.options', {}, 60000)
      return (res?.providers || [])
        .filter(p => p.authenticated !== false && (p.models || []).length)
        .map(p => ({ slug: p.slug, name: p.name || p.slug, models: p.models }))
    }
  })
}

// ───────────────────────────── Add Account Component ─────────────────────────────

function AddAccountInline({ type, onDone }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState('idle') // idle | auth | code
  const [session, setSession] = useState(null)
  const [url, setUrl] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const isAgy = type === 'antigravity'
  const title = isAgy ? '+ Add Antigravity Account' : '+ Add Claude Account'

  const startLogin = async () => {
    setBusy(true)
    setErr('')
    try {
      const endpoint = isAgy ? '/agy/login/start' : '/claude/login/start'
      const r = await api(endpoint, { method: 'POST', body: { open_browser: true } })
      setSession(r.session)
      setUrl(r.url)
      setStep('code')
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const finishLogin = async () => {
    if (!code.trim()) return
    setBusy(true)
    setErr('')
    try {
      const endpoint = isAgy ? '/agy/login/complete' : '/claude/login/complete'
      await api(endpoint, { method: 'POST', body: { session, code: code.trim() } })
      qc.invalidateQueries({ queryKey: KEY_STATUS })
      qc.invalidateQueries({ queryKey: KEY_AUTO })
      host.notify({ kind: 'success', message: `Added ${isAgy ? 'Antigravity' : 'Claude'} account successfully!` })
      setStep('idle')
      setOpen(false)
      setCode('')
      if (onDone) onDone()
    } catch (e) {
      setErr(String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return h(
      'div',
      { className: 'mmr-row', style: { paddingTop: 6 } },
      h(Button, { size: 'sm', variant: 'secondary', onClick: () => { setOpen(true); startLogin() } }, h(Codicon, { name: 'add' }), title)
    )
  }

  return h(
    'div',
    { className: 'mmr-loginbox' },
    h('div', { className: 'mmr-strong' }, isAgy ? 'Sign In: Google / Antigravity' : 'Sign In: Claude (Anthropic)'),
    h('div', { className: 'mmr-muted' }, 'A private browser window was opened for sign in. Copy the authorization code and paste it below:'),
    h(
      'div',
      { className: 'mmr-row' },
      h(Input, { placeholder: 'Paste Authorization Code here...', value: code, onChange: e => setCode(e.target.value) }),
      h(Button, { size: 'sm', disabled: busy || !code.trim(), onClick: finishLogin }, busy ? 'Submitting...' : 'Complete Sign In'),
      h(Button, { size: 'sm', variant: 'ghost', onClick: () => { setOpen(false); setStep('idle'); setCode(''); setErr('') } }, 'Cancel')
    ),
    url ? h('div', { className: 'mmr-row' },
      h('button', { type: 'button', className: 'mmr-faint', style: { background: 'none', border: 'none', textDecoration: 'underline', cursor: 'pointer' }, onClick: () => CTX.os.openExternal(url) }, 'Click here to re-open sign-in link in browser'),
      h('button', { type: 'button', className: 'mmr-faint', style: { background: 'none', border: 'none', textDecoration: 'underline', cursor: 'pointer' }, onClick: () => CTX.os.writeClipboard(url) }, 'Copy link')
    ) : null,
    err ? h('div', { style: { color: RED, fontSize: '0.75rem' } }, err) : null
  )
}

// ───────────────────────────── Model Picker Modal ─────────────────────────────

function ModelPicker({ catalog, onPick, onBack, title }) {
  const [q, setQ] = useState('')
  const needle = q.trim().toLowerCase()
  const groups = (catalog.data || [])
    .map(p => ({
      ...p,
      models: p.models.filter(m => !needle || m.toLowerCase().includes(needle) || p.name.toLowerCase().includes(needle))
    }))
    .filter(p => p.models.length)

  return h(
    'div',
    { className: 'mmr-sec' },
    h(
      'div',
      { className: 'mmr-row' },
      h('button', { type: 'button', className: 'mmr-ib', onClick: onBack }, h(Codicon, { name: 'chevron-left' })),
      h('span', { className: 'mmr-strong' }, title)
    ),
    h(Input, { value: q, placeholder: 'Search models…', autoFocus: true, onChange: e => setQ(e.target.value) }),
    h(
      'div',
      { className: 'mmr-list' },
      groups.map(p => [
        h('div', { key: `g-${p.slug}`, className: 'mmr-title', style: { padding: '6px 2px 2px' } }, p.name),
        p.models.map(m =>
          h(
            'button',
            { key: `${p.slug}-${m}`, type: 'button', className: 'mmr-item btn', onClick: () => onPick({ provider: p.slug, model: m, label: `${p.name} · ${m}` }) },
            h('span', { className: 'mmr-text mmr-grow mmr-trunc' }, m)
          )
        )
      ])
    )
  )
}

// ───────────────────────────── Auto Switch Popover Panel ─────────────────────────────

function AutoPanel({ onClose }) {
  const qc = useQueryClient()
  const auto = useAuto()
  const catalog = useModelCatalog()
  const [view, setView] = useState('main')
  const d = auto.data

  const save = async patch => {
    try {
      const r = await api('/autoswitch', { method: 'PUT', body: patch, timeoutMs: 60000 })
      qc.setQueryData(KEY_AUTO, r)
    } catch (e) {
      host.notify({ kind: 'error', message: String(e.message || e) })
    }
  }

  if (!d) return h('div', { className: 'mmr-pop' }, h('span', { className: 'mmr-muted' }, 'Loading router…'))

  if (view === 'default') {
    return h(
      'div',
      { className: 'mmr-pop' },
      h(ModelPicker, {
        catalog,
        title: 'Select default model',
        onBack: () => setView('main'),
        onPick: async e => {
          await save({ default: e })
          setView('main')
        }
      })
    )
  }

  if (view === 'add') {
    return h(
      'div',
      { className: 'mmr-pop' },
      h(ModelPicker, {
        catalog,
        title: 'Add to priority list',
        onBack: () => setView('main'),
        onPick: async e => {
          await save({ priority: [...(d.priority || []), e] })
          setView('main')
        }
      })
    )
  }

  const def = d.default || {}
  const priority = d.priority || []

  const move = (i, dir) => {
    const next = priority.slice()
    const j = i + dir
    if (j < 0 || j >= next.length) return
    ;[next[i], next[j]] = [next[j], next[i]]
    save({ priority: next })
  }
  const remove = i => save({ priority: priority.filter((_, k) => k !== i) })

  return h(
    'div',
    { className: 'mmr-pop' },
    h(
      'div',
      { className: 'mmr-sechead' },
      h('div', { className: 'mmr-row' }, h(Codicon, { name: 'layers' }), h('span', { className: 'mmr-strong' }, 'Model Auto Switching')),
      h(Switch, { checked: !!d.enabled, onCheckedChange: v => save({ enabled: !!v }) })
    ),
    h('div', { className: 'mmr-muted' }, d.enabled ? 'Enabled — requests will start on Default model, and failover through Priority list.' : 'Disabled — only selected model is used.'),
    h(
      'div',
      { className: 'mmr-sec' },
      h('div', { className: 'mmr-title' }, 'Default Model'),
      h(
        'button',
        { type: 'button', className: 'mmr-item btn active', onClick: () => setView('default') },
        h(Dot, { color: GREEN }),
        h(
          'div',
          { className: 'mmr-grow' },
          h('div', { className: 'mmr-text mmr-trunc' }, def.label || def.model || 'Select model'),
          h('div', { className: 'mmr-faint mmr-trunc' }, `${def.provider || ''} · ${def.model || ''}`)
        ),
        h('span', { className: 'mmr-badge' }, 'Change')
      )
    ),
    h(
      'div',
      { className: 'mmr-sec' },
      h(
        'div',
        { className: 'mmr-sechead' },
        h('div', { className: 'mmr-title' }, 'Priority Failover List'),
        h('button', { type: 'button', className: 'mmr-badge', style: { cursor: 'pointer' }, onClick: () => setView('add') }, '+ Add Model')
      ),
      priority.length
        ? priority.map((p, i) =>
            h(
              'div',
              { key: `${p.provider}-${p.model}-${i}`, className: 'mmr-item' },
              h('span', { className: 'mmr-idx' }, String(i + 1)),
              h(Dot, { color: GREEN }),
              h(
                'div',
                { className: 'mmr-grow' },
                h('div', { className: 'mmr-text mmr-trunc' }, p.label || p.model),
                h('div', { className: 'mmr-faint mmr-trunc' }, p.provider)
              ),
              h(IconBtn, { name: 'arrow-up', label: 'Higher priority', disabled: i === 0, onClick: () => move(i, -1) }),
              h(IconBtn, { name: 'arrow-down', label: 'Lower priority', disabled: i === priority.length - 1, onClick: () => move(i, 1) }),
              h(IconBtn, { name: 'close', label: 'Remove', danger: true, onClick: () => remove(i) })
            )
          )
        : h('div', { className: 'mmr-muted' }, 'No failover models added yet.')
    )
  )
}

function AutoToggle() {
  const auto = useAuto()
  const [open, setOpen] = useState(false)
  const d = auto.data
  const on = !!d?.enabled

  return h(
    Popover,
    { open, onOpenChange: setOpen },
    h(
      Tip,
      { label: on ? 'Model Router: Auto switching ON' : 'Model Router: Auto switching OFF' },
      h(
        PopoverTrigger,
        { asChild: true },
        h('button', { type: 'button', className: `mmr-pill${on ? ' on' : ''}` }, 'Auto')
      )
    ),
    h(
      PopoverContent,
      {
        side: 'top',
        align: 'end',
        sideOffset: 8,
        className: 'p-0',
        style: { width: 'min(24rem, calc(100vw - 24px))', maxHeight: 'min(34rem, calc(100vh - 120px))', overflowY: 'auto' }
      },
      open ? h(AutoPanel, { onClose: () => setOpen(false) }) : null
    )
  )
}

// ───────────────────────────── Main Sidebar Page ─────────────────────────────

function Page() {
  const status = useStatus()
  const qc = useQueryClient()
  const s = status.data

  const startAll = async () => {
    await api('/proxies/start', { method: 'POST' })
    qc.invalidateQueries({ queryKey: KEY_STATUS })
    host.notify({ kind: 'success', message: 'All Antigravity & Claude proxies started!' })
  }
  const stopAll = async () => {
    await api('/proxies/stop', { method: 'POST' })
    qc.invalidateQueries({ queryKey: KEY_STATUS })
    host.notify({ kind: 'success', message: 'All proxies stopped.' })
  }

  const deleteAgy = async (slot) => {
    await api(`/agy/accounts/${slot}`, { method: 'DELETE' })
    qc.invalidateQueries({ queryKey: KEY_STATUS })
    host.notify({ kind: 'success', message: `Antigravity account ${slot} removed.` })
  }

  const deleteClaude = async (slot) => {
    await api(`/claude/accounts/${slot}`, { method: 'DELETE' })
    qc.invalidateQueries({ queryKey: KEY_STATUS })
    host.notify({ kind: 'success', message: `Claude account ${slot} removed.` })
  }

  return h(
    'div',
    { className: 'mmr-page' },
    h(
      'div',
      { className: 'mmr-wrap' },
      h('div', { className: 'mmr-h1' }, h(Codicon, { name: 'layers' }), 'Model Router'),
      h(
        'div',
        { className: 'mmr-card' },
        h('div', { className: 'mmr-title' }, 'Global Proxy Status'),
        h(
          'div',
          { className: 'mmr-row' },
          h(Dot, { color: s?.state === 'on' ? GREEN : s?.state === 'partial' ? YELLOW : RED }),
          h('span', { className: 'mmr-strong' }, s?.state === 'on' ? 'All Proxies Active' : s?.state === 'partial' ? 'Some Proxies Active' : 'Proxies Stopped'),
          h('span', { className: 'mmr-muted mmr-grow' }, `(${s?.running_proxies || 0} / ${s?.total_accounts || 0} running)`),
          h(Button, { size: 'xs', onClick: startAll }, 'Turn On All'),
          h(Button, { size: 'xs', variant: 'secondary', onClick: stopAll }, 'Turn Off All')
        )
      ),
      h(
        'div',
        { className: 'mmr-card' },
        h('div', { className: 'mmr-title' }, `Antigravity Accounts (${s?.antigravity?.count || 0})`),
        (s?.antigravity?.accounts || []).map(a =>
          h(
            'div',
            { key: `agy-${a.slot}`, className: 'mmr-acc mmr-row' },
            h(Dot, { color: a.proxy ? GREEN : RED }),
            h(
              'div',
              { className: 'mmr-grow' },
              h('div', { className: 'mmr-text mmr-trunc' }, a.email),
              h('div', { className: 'mmr-faint' }, `Slot ${a.slot} · Port :${a.port}`)
            ),
            a.remaining != null ? h('span', { className: 'mmr-badge' }, `${Math.round(a.remaining * 100)}% left`) : null,
            h(IconBtn, { name: 'trash', label: 'Delete account', danger: true, onClick: () => deleteAgy(a.slot) })
          )
        ),
        h(AddAccountInline, { type: 'antigravity' })
      ),
      h(
        'div',
        { className: 'mmr-card' },
        h('div', { className: 'mmr-title' }, `Claude Accounts (${s?.claude?.count || 0})`),
        (s?.claude?.accounts || []).map(a =>
          h(
            'div',
            { key: `claude-${a.slot}`, className: 'mmr-acc mmr-row' },
            h(Dot, { color: a.proxy ? GREEN : RED }),
            h(
              'div',
              { className: 'mmr-grow' },
              h('div', { className: 'mmr-text mmr-trunc' }, a.email),
              h('div', { className: 'mmr-faint' }, `Slot ${a.slot} · Port :${a.port}`)
            ),
            a.used != null ? h('span', { className: 'mmr-badge' }, `${Math.round(a.used)}% used`) : null,
            h(IconBtn, { name: 'trash', label: 'Delete account', danger: true, onClick: () => deleteClaude(a.slot) })
          )
        ),
        h(AddAccountInline, { type: 'claude' })
      )
    )
  )
}

export default {
  id: ID,
  name: 'Model Router',
  defaultEnabled: true,
  register(ctx) {
    CTX = ctx
    injectCss()
    ctx.register({
      id: 'page',
      area: ROUTES_AREA,
      title: 'Model Router',
      data: { path: '/model-router' },
      render: () => h(Page, {})
    })
    ctx.register({
      id: 'nav',
      area: SIDEBAR_NAV_AREA,
      data: { path: '/model-router', label: 'Model Router', codicon: 'layers' }
    })
    ctx.register({
      id: 'auto-switch',
      area: COMPOSER_AREAS.actions,
      order: 0,
      render: () => h(AutoToggle, {})
    })
  }
}
