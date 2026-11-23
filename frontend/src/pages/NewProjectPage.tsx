import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Layout } from '../components/Layout'
import type { LocationItem, SerpWindow, Target } from '../types'

type ImportStats = {
  loaded: number
  unique: number
  duplicates_removed: number
  invalid: number
  linked_to_project: number
  invalid_samples: string[]
}

type Estimate = {
  unique_keywords: number
  region_language_pairs: number
  query_combinations: number
  planned_months: number
  max_planned_snapshots: number
  estimated_cost_usd: string
  note: string
}

export function NewProjectPage() {
  const nav = useNavigate()
  const [win, setWin] = useState<SerpWindow | null>(null)
  const [name, setName] = useState('')
  const [keywordsText, setKeywordsText] = useState('')
  const [kwFile, setKwFile] = useState<File | null>(null)
  const [locQuery, setLocQuery] = useState('Australia')
  const [locHits, setLocHits] = useState<LocationItem[]>([])
  const [targets, setTargets] = useState<Target[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [depth, setDepth] = useState<10 | 20 | 50 | 100>(100)
  const [budget, setBudget] = useState('1.00')
  const [dedupe, setDedupe] = useState<'registrable_domain' | 'hostname'>('registrable_domain')
  const [availMode, setAvailMode] = useState<'manual_after_serp' | 'auto_after_serp' | 'off'>(
    'manual_after_serp',
  )
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [importStats, setImportStats] = useState<ImportStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function importKeywords(projectId: string): Promise<ImportStats> {
    if (kwFile) {
      const form = new FormData()
      form.append('file', kwFile)
      return api.postForm<ImportStats>(`/api/projects/${projectId}/keywords/import-file`, form)
    }
    return api.post<ImportStats>(`/api/projects/${projectId}/keywords/import`, {
      text: keywordsText,
    })
  }

  useEffect(() => {
    void api.get<SerpWindow>('/api/meta/serp-window').then((w) => {
      setWin(w)
      // default: last full month inside window (spike-friendly)
      const today = new Date(w.today + 'T00:00:00')
      const end = new Date(today.getFullYear(), today.getMonth(), 0)
      const start = new Date(end.getFullYear(), end.getMonth(), 1)
      const clamp = (d: Date) => {
        const earliest = new Date(w.earliest_allowed_date + 'T00:00:00')
        if (d < earliest) return earliest
        if (d > today) return today
        return d
      }
      const s = clamp(start)
      const e = clamp(end)
      setDateFrom(s.toISOString().slice(0, 10))
      setDateTo(e.toISOString().slice(0, 10))
    })
  }, [])

  async function searchLocations() {
    const data = await api.get<{ items: LocationItem[] }>(
      `/api/locations?q=${encodeURIComponent(locQuery)}`,
    )
    setLocHits(data.items.slice(0, 12))
  }

  function addTarget(loc: LocationItem, language_code: string) {
    const next: Target = {
      location_code: loc.location_code,
      location_name: loc.location_name,
      language_code,
    }
    setTargets((prev) => {
      if (prev.some((t) => t.location_code === next.location_code && t.language_code === next.language_code)) {
        return prev
      }
      return [...prev, next]
    })
  }

  const windowNote = useMemo(() => {
    if (!win) return ''
    return `Allowed history: ${win.earliest_allowed_date} → ${win.today} (${win.max_history_days}d). Source: ${win.provider_primary}.`
  }, [win])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (!name.trim()) throw new Error('Project name required')
      if (!keywordsText.trim() && !kwFile) throw new Error('Keywords text or import file required')
      if (!targets.length) throw new Error('Add at least one location / language')
      if (!dateFrom || !dateTo) throw new Error('Period required')
      if (win && dateFrom < win.earliest_allowed_date) {
        throw new Error(`date_from cannot be before ${win.earliest_allowed_date}`)
      }

      const project = await api.post<{ id: string }>('/api/projects', { name: name.trim() })
      const stats = await importKeywords(project.id)
      setImportStats(stats)
      await api.put(`/api/projects/${project.id}/targets`, { targets })

      const est = await api.post<Estimate>(`/api/projects/${project.id}/runs/estimate`, {
        date_from: dateFrom,
        date_to: dateTo,
      })
      setEstimate(est)

      const run = await api.post<{ id: string }>(`/api/projects/${project.id}/runs`, {
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
      setError(err instanceof Error ? err.message : 'Failed')
    } finally {
      setBusy(false)
    }
  }

  async function onEstimateOnly() {
    setError(null)
    setBusy(true)
    try {
      if (!keywordsText.trim() && !kwFile) throw new Error('Keywords text or import file required')
      if (!targets.length) throw new Error('Add at least one location / language')
      const project = await api.post<{ id: string }>('/api/projects', {
        name: name.trim() || `draft-${Date.now()}`,
      })
      const stats = await importKeywords(project.id)
      setImportStats(stats)
      await api.put(`/api/projects/${project.id}/targets`, { targets })
      const est = await api.post<Estimate>(`/api/projects/${project.id}/runs/estimate`, {
        date_from: dateFrom,
        date_to: dateTo,
      })
      setEstimate(est)
      // stay on page; user can open project to run later — store id in hint
      setError(null)
      nav(`/projects/${project.id}?estimated=1`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Estimate failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Layout note={windowNote}>
      <form className="panel" onSubmit={onSubmit}>
        <h2>New project & SERP run</h2>
        <div className="banner banner-info">
          Organic only. History older than ~365 days is blocked by the provider (Spike). Do not advertise
          2021–2024 depth in this UI.
        </div>
        {error && <div className="banner banner-error">{error}</div>}

        <div className="grid-2">
          <div>
            <div className="field">
              <label htmlFor="pname">Project name</label>
              <input id="pname" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="kw">Keywords (one per line)</label>
              <textarea
                id="kw"
                value={keywordsText}
                onChange={(e) => {
                  setKeywordsText(e.target.value)
                  if (e.target.value.trim()) setKwFile(null)
                }}
                placeholder={'amazon\ncasino'}
                required={!kwFile}
              />
              <span className="hint">UTF-8; duplicates removed on import. Max 700 chars per keyword.</span>
            </div>
            <div className="field">
              <label htmlFor="kwfile">Import file (§4.1)</label>
              <input
                id="kwfile"
                type="file"
                accept=".txt,.csv,text/plain,text/csv"
                onChange={(e) => {
                  const f = e.target.files?.[0] || null
                  setKwFile(f)
                  if (f) setKeywordsText('')
                }}
              />
              <span className="hint">
                Alternative to paste: `.txt` / `.csv` UTF-8 (BOM ok). CSV uses column `keyword` or the first
                column. {kwFile ? `Selected: ${kwFile.name}` : ''}
              </span>
            </div>
            {importStats && (
              <div className="stats">
                <span className="stat">
                  loaded <b>{importStats.loaded}</b>
                </span>
                <span className="stat">
                  unique <b>{importStats.unique}</b>
                </span>
                <span className="stat">
                  dupes <b>{importStats.duplicates_removed}</b>
                </span>
                <span className="stat">
                  invalid <b>{importStats.invalid}</b>
                </span>
              </div>
            )}
          </div>

          <div>
            <div className="field">
              <label htmlFor="loc">Locations</label>
              <div className="toolbar">
                <input
                  id="loc"
                  value={locQuery}
                  onChange={(e) => setLocQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), void searchLocations())}
                />
                <button type="button" className="btn" onClick={() => void searchLocations()}>
                  Search
                </button>
              </div>
              {locHits.length > 0 && (
                <div className="loc-results">
                  {locHits.map((loc) => {
                    const langs = loc.languages?.length
                      ? loc.languages
                      : [{ language_code: 'en', language_name: 'English' }]
                    return langs.slice(0, 4).map((lg) => (
                      <button
                        key={`${loc.location_code}-${lg.language_code}`}
                        type="button"
                        onClick={() => addTarget(loc, lg.language_code)}
                      >
                        {loc.location_name} ({loc.country_iso_code || loc.location_code}) · {lg.language_code}
                      </button>
                    ))
                  })}
                </div>
              )}
              <div className="chips">
                {targets.map((t) => (
                  <span className="chip" key={`${t.location_code}-${t.language_code}`}>
                    {t.location_name} / {t.language_code}
                    <button
                      type="button"
                      aria-label="Remove"
                      onClick={() =>
                        setTargets((prev) =>
                          prev.filter(
                            (x) =>
                              !(x.location_code === t.location_code && x.language_code === t.language_code),
                          ),
                        )
                      }
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            <div className="grid-2">
              <div className="field">
                <label htmlFor="df">Date from</label>
                <input
                  id="df"
                  type="date"
                  value={dateFrom}
                  min={win?.earliest_allowed_date}
                  max={win?.today}
                  onChange={(e) => setDateFrom(e.target.value)}
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="dt">Date to</label>
                <input
                  id="dt"
                  type="date"
                  value={dateTo}
                  min={win?.earliest_allowed_date}
                  max={win?.today}
                  onChange={(e) => setDateTo(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="grid-2">
              <div className="field">
                <label htmlFor="depth">SERP depth (organic)</label>
                <select
                  id="depth"
                  value={depth}
                  onChange={(e) => setDepth(Number(e.target.value) as 10 | 20 | 50 | 100)}
                >
                  <option value={10}>TOP-10</option>
                  <option value={20}>TOP-20</option>
                  <option value={50}>TOP-50</option>
                  <option value={100}>TOP-100</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="budget">SERP budget USD</label>
                <input
                  id="budget"
                  type="number"
                  min="0.0001"
                  step="0.01"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  required
                />
              </div>
            </div>

            <div className="grid-2">
              <div className="field">
                <label htmlFor="dedupe">Dedupe mode (unique TXT)</label>
                <select
                  id="dedupe"
                  value={dedupe}
                  onChange={(e) => setDedupe(e.target.value as 'registrable_domain' | 'hostname')}
                >
                  <option value="registrable_domain">registrable_domain</option>
                  <option value="hostname">hostname</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="amode">Availability mode</label>
                <select
                  id="amode"
                  value={availMode}
                  onChange={(e) =>
                    setAvailMode(e.target.value as 'manual_after_serp' | 'auto_after_serp' | 'off')
                  }
                >
                  <option value="manual_after_serp">Manual after SERP</option>
                  <option value="auto_after_serp">Auto after SERP</option>
                  <option value="off">Off</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        {estimate && (
          <div className="banner banner-info">
            Estimate: {estimate.query_combinations} combos × {estimate.planned_months} month(s) ≤{' '}
            {estimate.max_planned_snapshots} snapshots ≈ ${estimate.estimated_cost_usd} (reference).
          </div>
        )}

        <div className="toolbar">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Starting…' : 'Create & start SERP run'}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => void onEstimateOnly()}>
            Save project + estimate (no run)
          </button>
        </div>
      </form>
    </Layout>
  )
}
