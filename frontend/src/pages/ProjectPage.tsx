import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Layout, StatusBadge } from '../components/Layout'
import type { SerpWindow, Target } from '../types'

type ProjectDetail = {
  id: string
  name: string
  keywords: number
  targets: number
  target_list: Target[]
  created_at: string | null
}

type RunRow = {
  id: string
  status: string
  date_from: string
  date_to: string
  depth: number
  spent_usd: string
  budget_cap: string
  created_at: string | null
}

export function ProjectPage() {
  const { projectId } = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [runs, setRuns] = useState<RunRow[]>([])
  const [win, setWin] = useState<SerpWindow | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [depth, setDepth] = useState(100)
  const [budget, setBudget] = useState('1.00')
  const [dedupe, setDedupe] = useState('registrable_domain')
  const [availMode, setAvailMode] = useState('manual_after_serp')
  const [estimate, setEstimate] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [kwText, setKwText] = useState('')
  const [kwFile, setKwFile] = useState<File | null>(null)
  const [importMsg, setImportMsg] = useState<string | null>(null)

  async function refreshProject() {
    if (!projectId) return
    const p = await api.get<ProjectDetail>(`/api/projects/${projectId}`)
    setProject(p)
  }

  async function onImportKeywords() {
    if (!projectId) return
    setError(null)
    setImportMsg(null)
    setBusy(true)
    try {
      if (!kwText.trim() && !kwFile) throw new Error('Paste keywords or choose a .txt/.csv file')
      let stats: { loaded: number; unique: number; linked_to_project: number; invalid: number }
      if (kwFile) {
        const form = new FormData()
        form.append('file', kwFile)
        stats = await api.postForm(`/api/projects/${projectId}/keywords/import-file`, form)
      } else {
        stats = await api.post(`/api/projects/${projectId}/keywords/import`, { text: kwText })
      }
      setImportMsg(
        `Imported loaded=${stats.loaded} unique=${stats.unique} linked=${stats.linked_to_project} invalid=${stats.invalid}`,
      )
      setKwText('')
      setKwFile(null)
      await refreshProject()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!projectId) return
    void (async () => {
      const [p, r, w] = await Promise.all([
        api.get<ProjectDetail>(`/api/projects/${projectId}`),
        api.get<{ items: RunRow[] }>(`/api/projects/${projectId}/runs`),
        api.get<SerpWindow>('/api/meta/serp-window'),
      ])
      setProject(p)
      setRuns(r.items)
      setWin(w)
      const today = new Date(w.today + 'T00:00:00')
      const end = new Date(today.getFullYear(), today.getMonth(), 0)
      const start = new Date(end.getFullYear(), end.getMonth(), 1)
      setDateFrom(start.toISOString().slice(0, 10))
      setDateTo(end.toISOString().slice(0, 10))
    })().catch((err) => setError(err instanceof Error ? err.message : 'Load failed'))
  }, [projectId])

  async function onEstimate() {
    if (!projectId) return
    const est = await api.post<{
      max_planned_snapshots: number
      estimated_cost_usd: string
      planned_months: number
      query_combinations: number
    }>(`/api/projects/${projectId}/runs/estimate`, { date_from: dateFrom, date_to: dateTo })
    setEstimate(
      `${est.query_combinations} combos · ${est.planned_months} mo · ≤${est.max_planned_snapshots} snaps · ~$${est.estimated_cost_usd}`,
    )
  }

  async function onStart(e: FormEvent) {
    e.preventDefault()
    if (!projectId) return
    setBusy(true)
    setError(null)
    try {
      await onEstimate()
      const run = await api.post<{ id: string }>(`/api/projects/${projectId}/runs`, {
        date_from: dateFrom,
        date_to: dateTo,
        depth,
        budget_cap: budget,
        dedupe_mode: dedupe,
        availability_mode: availMode,
        start: true,
      })
      nav(`/runs/${run.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Start failed')
    } finally {
      setBusy(false)
    }
  }

  if (!project) {
    return (
      <Layout>
        {error ? <div className="banner banner-error">{error}</div> : <div className="empty">Loading…</div>}
      </Layout>
    )
  }

  return (
    <Layout>
      {sp.get('estimated') && (
        <div className="banner banner-info">Project saved with estimate. Start a run below when ready.</div>
      )}
      {error && <div className="banner banner-error">{error}</div>}

      <div className="panel">
        <h2>{project.name}</h2>
        <div className="stats">
          <span className="stat">
            keywords <b>{project.keywords}</b>
          </span>
          <span className="stat">
            targets <b>{project.targets}</b>
          </span>
        </div>
        <div className="chips" style={{ marginTop: '0.75rem' }}>
          {project.target_list?.map((t) => (
            <span className="chip" key={`${t.location_code}-${t.language_code}`}>
              {t.location_name} / {t.language_code}
            </span>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Import keywords (§4.1)</h3>
        <div className="field">
          <label htmlFor="pkw">Paste (one per line)</label>
          <textarea
            id="pkw"
            value={kwText}
            onChange={(e) => {
              setKwText(e.target.value)
              if (e.target.value.trim()) setKwFile(null)
            }}
            placeholder={'amazon\ncasino'}
          />
        </div>
        <div className="field">
          <label htmlFor="pkwfile">Or import file</label>
          <input
            id="pkwfile"
            type="file"
            accept=".txt,.csv,text/plain,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0] || null
              setKwFile(f)
              if (f) setKwText('')
            }}
          />
          <span className="hint">
            `.txt` / `.csv` UTF-8 (BOM ok). CSV: column `keyword` or first column.
            {kwFile ? ` Selected: ${kwFile.name}` : ''}
          </span>
        </div>
        {importMsg && <div className="banner banner-info">{importMsg}</div>}
        <button type="button" className="btn" disabled={busy} onClick={() => void onImportKeywords()}>
          Import keywords
        </button>
      </div>

      <form className="panel" onSubmit={onStart}>
        <h3>Start SERP run</h3>
        <div className="grid-2">
          <div className="field">
            <label>Date from</label>
            <input
              type="date"
              value={dateFrom}
              min={win?.earliest_allowed_date}
              max={win?.today}
              onChange={(e) => setDateFrom(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label>Date to</label>
            <input
              type="date"
              value={dateTo}
              min={win?.earliest_allowed_date}
              max={win?.today}
              onChange={(e) => setDateTo(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label>Depth</label>
            <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
              <option value={10}>TOP-10</option>
              <option value={20}>TOP-20</option>
              <option value={50}>TOP-50</option>
              <option value={100}>TOP-100</option>
            </select>
          </div>
          <div className="field">
            <label>Budget USD</label>
            <input type="number" step="0.01" min="0.0001" value={budget} onChange={(e) => setBudget(e.target.value)} />
          </div>
          <div className="field">
            <label>Dedupe</label>
            <select value={dedupe} onChange={(e) => setDedupe(e.target.value)}>
              <option value="registrable_domain">registrable_domain</option>
              <option value="hostname">hostname</option>
            </select>
          </div>
          <div className="field">
            <label>Availability mode</label>
            <select value={availMode} onChange={(e) => setAvailMode(e.target.value)}>
              <option value="manual_after_serp">Manual after SERP</option>
              <option value="auto_after_serp">Auto after SERP</option>
              <option value="off">Off</option>
            </select>
          </div>
        </div>
        {estimate && <div className="banner banner-info">{estimate}</div>}
        <div className="toolbar">
          <button type="button" className="btn" onClick={() => void onEstimate()}>
            Estimate
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy || project.keywords < 1 || project.targets < 1}>
            Start run
          </button>
        </div>
      </form>

      <div className="panel">
        <h3>Runs</h3>
        {runs.length === 0 ? (
          <div className="empty">No runs yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Period</th>
                  <th>Depth</th>
                  <th>Spend</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="mono">
                      {r.date_from} → {r.date_to}
                    </td>
                    <td className="mono">{r.depth}</td>
                    <td className="mono">
                      ${r.spent_usd} / ${r.budget_cap}
                    </td>
                    <td className="mono">{r.created_at?.slice(0, 19)}</td>
                    <td>
                      <Link to={`/runs/${r.id}`}>Open</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  )
}
