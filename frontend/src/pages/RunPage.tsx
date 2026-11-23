import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, downloadAuthenticated } from '../api'
import { Layout, StatusBadge } from '../components/Layout'
import type {
  AvailabilityRow,
  CoverageMatrix,
  DomainRow,
  JobProgress,
  PageResult,
  PositionsPage,
  RunProgress,
} from '../types'

type Tab = 'domains' | 'positions' | 'coverage' | 'availability'

const ACTIVE = new Set(['QUEUED', 'RUNNING', 'PAUSED'])

export function RunPage() {
  const { runId } = useParams()
  const [tab, setTab] = useState<Tab>('domains')
  const [prog, setProg] = useState<RunProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [domains, setDomains] = useState<PageResult<DomainRow> | null>(null)
  const [positions, setPositions] = useState<PositionsPage | null>(null)
  const [coverageMatrix, setCoverageMatrix] = useState<CoverageMatrix | null>(null)
  const [availability, setAvailability] = useState<PageResult<AvailabilityRow> | null>(null)
  const [dq, setDq] = useState('')
  const [lastSeenBefore, setLastSeenBefore] = useState('')
  const [domSort, setDomSort] = useState('keywords_found')
  const [domOrder, setDomOrder] = useState('desc')
  const [domainsAvailableOnly, setDomainsAvailableOnly] = useState(false)
  const [posKw, setPosKw] = useState('')
  const [posDomain, setPosDomain] = useState('')
  const [posLoc, setPosLoc] = useState('')
  const [posLang, setPosLang] = useState('')
  const [posMonth, setPosMonth] = useState('')
  const [posTld, setPosTld] = useState('')
  const [posSource, setPosSource] = useState('')
  const [posRankMax, setPosRankMax] = useState('')
  const [covStatus, setCovStatus] = useState('')
  const [covKw, setCovKw] = useState('')
  const [covLoc, setCovLoc] = useState('')
  const [availOnly, setAvailOnly] = useState(false)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [cardDomain, setCardDomain] = useState<string | null>(null)
  const [card, setCard] = useState<Record<string, unknown> | null>(null)
  const [job, setJob] = useState<JobProgress | null>(null)
  const [availBudget, setAvailBudget] = useState('50')
  const [availEst, setAvailEst] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [exportAll, setExportAll] = useState(false)

  const refreshProgress = useCallback(async () => {
    if (!runId) return
    const p = await api.get<RunProgress>(`/api/runs/${runId}`)
    setProg(p)
    return p
  }, [runId])

  useEffect(() => {
    if (!runId) return
    let stop = false
    const tick = async () => {
      try {
        const p = await refreshProgress()
        if (stop || !p) return
        if (ACTIVE.has(p.status)) {
          window.setTimeout(tick, 2500)
        }
      } catch (err) {
        if (!stop) setError(err instanceof Error ? err.message : 'Progress failed')
      }
    }
    void tick()
    return () => {
      stop = true
    }
  }, [runId, refreshProgress])

  const budgetPct = useMemo(() => {
    if (!prog) return 0
    const spent = Number(prog.spent_usd)
    const cap = Number(prog.budget_cap)
    if (!cap) return 0
    return Math.min(100, Math.round((spent / cap) * 100))
  }, [prog])

  const doneQueries = useMemo(() => {
    if (!prog) return 0
    const s = prog.queries_by_status || {}
    return (s.COMPLETED || 0) + (s.FAILED || 0) + (s.CANCELED || 0)
  }, [prog])

  async function loadTab(nextTab = tab, nextPage = page) {
    if (!runId) return
    setError(null)
    try {
      if (nextTab === 'domains') {
        const qs = new URLSearchParams({
          page: String(nextPage),
          page_size: '50',
          sort: domSort,
          order: domOrder,
        })
        if (dq) qs.set('q', dq)
        if (lastSeenBefore) qs.set('last_seen_before', lastSeenBefore)
        if (domainsAvailableOnly) qs.set('available_only', 'true')
        setDomains(await api.get(`/api/runs/${runId}/domains?${qs}`))
      } else if (nextTab === 'positions') {
        const qs = new URLSearchParams({ page: String(nextPage), page_size: '50' })
        if (posKw) qs.set('keyword', posKw)
        if (posDomain) qs.set('domain', posDomain)
        if (posLoc) qs.set('location_code', posLoc)
        if (posLang) qs.set('language', posLang)
        if (posMonth) qs.set('month', posMonth)
        if (posTld) qs.set('tld', posTld)
        if (posSource) qs.set('source', posSource)
        if (posRankMax) qs.set('rank_max', posRankMax)
        setPositions(await api.get(`/api/runs/${runId}/positions?${qs}`))
      } else if (nextTab === 'coverage') {
        const qs = new URLSearchParams({
          keyword_page: String(nextPage),
          keyword_page_size: '15',
        })
        if (covStatus) qs.set('status', covStatus)
        if (covKw) qs.set('keyword', covKw)
        if (covLoc) qs.set('location_code', covLoc)
        setCoverageMatrix(await api.get(`/api/runs/${runId}/coverage/matrix?${qs}`))
      } else {
        const qs = new URLSearchParams({ page: String(nextPage), page_size: '50' })
        if (availOnly) qs.set('available_only', 'true')
        setAvailability(await api.get(`/api/runs/${runId}/availability?${qs}`))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Load failed')
    }
  }

  useEffect(() => {
    if (!prog) return
    if (!ACTIVE.has(prog.status) || tab === 'coverage') {
      void loadTab(tab, page)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prog?.status, tab, page])

  async function openCard(domain: string) {
    if (!runId) return
    setCardDomain(domain)
    setCard(await api.get(`/api/runs/${runId}/domains/${encodeURIComponent(domain)}`))
  }

  async function act(path: string) {
    if (!runId) return
    await api.post(`/api/runs/${runId}/${path}`)
    await refreshProgress()
  }

  async function exportSerp() {
    if (!runId) return
    setMsg(null)
    const body: Record<string, unknown> = { export_all: exportAll }
    if (!exportAll) {
      if (dq) body.q = dq
      if (lastSeenBefore) body.last_seen_before = lastSeenBefore
      if (domainsAvailableOnly) body.available_only = true
      if (posKw) {
        body.keyword = posKw
        body.pos_keyword = posKw
      }
      if (posDomain) {
        body.domain = posDomain
        body.pos_domain = posDomain
      }
      if (posLoc) body.location_code = Number(posLoc)
      if (posLang) body.language = posLang
      if (posMonth) body.month = posMonth
      if (posTld) body.pos_tld = posTld
      if (posSource) {
        body.source = posSource
        body.pos_source = posSource
      }
      if (posRankMax) body.rank_max = Number(posRankMax)
      if (covStatus) body.coverage_status = covStatus
      if (covKw) body.coverage_keyword = covKw
    }
    const exp = await api.post<{ export_id: string; files: string[]; filters_applied?: unknown }>(
      `/api/runs/${runId}/exports`,
      body,
    )
    for (const f of exp.files) {
      await downloadAuthenticated(
        `/api/exports/${exp.export_id}/files/${f}?run_id=${runId}`,
        f,
      )
    }
    setMsg(
      `SERP export ${exp.export_id}${exportAll ? ' (all)' : ' (filtered)'}: ${exp.files.join(', ')}`,
    )
  }

  async function exportAvail() {
    if (!runId) return
    const body: Record<string, unknown> = {
      export_all: exportAll,
      available_only: !exportAll && availOnly,
    }
    if (!exportAll) {
      if (dq) body.q = dq
      if (lastSeenBefore) body.last_seen_before = lastSeenBefore
    }
    const exp = await api.post<{ export_id: string; files: string[] }>(
      `/api/runs/${runId}/availability/export`,
      body,
    )
    for (const f of exp.files) {
      await downloadAuthenticated(
        `/api/exports/${exp.export_id}/availability/${f}?run_id=${runId}`,
        f,
      )
    }
    setMsg(
      `Availability export ${exp.export_id}${exportAll ? ' (all)' : ' (filtered)'}: ${exp.files.join(', ')}`,
    )
  }

  async function estimateAvail() {
    if (!runId) return
    const est = await api.post<{
      total_unique: number
      cached_fresh: number
      to_check: number
      projected_credits: number
      projected_usd: string
    }>(`/api/runs/${runId}/availability/estimate`, { force_refresh: false })
    setAvailEst(
      `unique ${est.total_unique} · cached ${est.cached_fresh} · to_check ${est.to_check} · ~${est.projected_credits} credits / $${est.projected_usd}`,
    )
    if (est.to_check > 0) setAvailBudget(String(Math.max(est.to_check, 1)))
  }

  async function startAvail(mode: 'all_unique' | 'filtered', forceRefresh = false) {
    if (!runId) return
    const body: Record<string, unknown> = {
      budget_cap_credits: Number(availBudget),
      force_refresh: forceRefresh,
      mode,
      start: true,
    }
    if (mode === 'filtered') {
      const list = [...selected]
      if (!list.length) {
        setError('Select domains first')
        return
      }
      body.domains = list
      body.mode = 'filtered'
    }
    const res = await api.post<{ job_id: string; progress: JobProgress }>(
      `/api/runs/${runId}/availability/jobs`,
      body,
    )
    setJob(res.progress)
    pollJob(res.job_id)
  }

  function pollJob(jobId: string) {
    const tick = async () => {
      const j = await api.get<JobProgress>(`/api/availability/jobs/${jobId}`)
      setJob(j)
      if (ACTIVE.has(j.status) || j.status === 'RUNNING' || j.status === 'QUEUED') {
        window.setTimeout(tick, 2000)
      } else {
        void loadTab('availability', 1)
        setTab('availability')
      }
    }
    void tick()
  }

  async function recheck(domain: string) {
    if (!runId) return
    const res = await api.post<{ job_id: string }>(
      `/api/domains/${encodeURIComponent(domain)}/availability/recheck?run_id=${runId}&budget_cap_credits=1`,
    )
    setMsg(`Verify now started for ${domain}`)
    const tick = async () => {
      const j = await api.get<JobProgress>(`/api/availability/jobs/${res.job_id}`)
      setJob(j)
      if (ACTIVE.has(j.status) || j.status === 'RUNNING' || j.status === 'QUEUED') {
        window.setTimeout(tick, 2000)
        return
      }
      setMsg(`Verify finished for ${domain}: ${j.status}`)
      if (cardDomain === domain) {
        void openCard(domain)
      }
      void loadTab(tab === 'availability' ? 'availability' : tab, page)
    }
    void tick()
  }

  async function confirmLive(domain: string) {
    try {
      await api.post(`/api/domains/${encodeURIComponent(domain)}/availability/confirm-live`)
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Confirm live unavailable (GoDaddy stub)')
    }
  }

  function toggleSel(domain: string) {
    setSelected((prev) => {
      const n = new Set(prev)
      if (n.has(domain)) n.delete(domain)
      else n.add(domain)
      return n
    })
  }

  if (!prog) {
    return (
      <Layout>
        {error ? <div className="banner banner-error">{error}</div> : <div className="empty">Loading run…</div>}
      </Layout>
    )
  }

  return (
    <Layout>
      {error && <div className="banner banner-error">{error}</div>}
      {msg && <div className="banner banner-info">{msg}</div>}
      {prog && (prog.budget_warning_80 || budgetPct >= 80) && (
        <div className={`banner ${budgetPct >= 100 || prog.status === 'BUDGET_EXCEEDED' ? 'banner-error' : 'banner-warn'}`}>
          SERP budget at {budgetPct}% (${prog.spent_usd} / ${prog.budget_cap})
          {prog.next_query_projected_usd
            ? ` · next query reserves ~$${prog.next_query_projected_usd}`
            : ''}
          {prog.can_afford_next_query === false ? ' · soft-stop: cannot afford another period' : ''}
        </div>
      )}

      <div className="panel">
        <div className="toolbar" style={{ justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0 }}>Run {prog.run_id.slice(0, 8)}…</h2>
            <p className="hint" style={{ margin: '0.25rem 0 0' }}>
              {prog.date_from} → {prog.date_to} · depth {prog.depth} · {prog.source}
            </p>
          </div>
          <StatusBadge status={prog.status} />
        </div>
        <div className="progress-bar">
          <span
            style={{
              width: `${prog.queries_total ? Math.round((doneQueries / prog.queries_total) * 100) : 0}%`,
            }}
          />
        </div>
        <div className="stats">
          <span className="stat">
            queries <b>{doneQueries}/{prog.queries_total}</b>
          </span>
          <span className="stat">
            snapshots <b>{prog.snapshots}</b>
          </span>
          <span className="stat">
            spend <b>${prog.spent_usd}</b>
          </span>
          {Object.entries(prog.queries_by_status || {}).map(([k, v]) => (
            <span className="stat" key={k}>
              {k} <b>{v}</b>
            </span>
          ))}
        </div>
        <div className="toolbar" style={{ marginTop: '0.75rem' }}>
          <button type="button" className="btn" disabled={prog.status !== 'RUNNING'} onClick={() => void act('pause')}>
            Pause
          </button>
          <button
            type="button"
            className="btn"
            disabled={!['PAUSED', 'QUEUED'].includes(prog.status)}
            onClick={() => void act('resume')}
          >
            Resume
          </button>
          <button
            type="button"
            className="btn btn-danger"
            disabled={['COMPLETED', 'COMPLETED_WITH_GAPS', 'CANCELED', 'FAILED'].includes(prog.status)}
            onClick={() => void act('cancel')}
          >
            Cancel
          </button>
          <label className="btn btn-ghost" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={exportAll}
              onChange={(e) => setExportAll(e.target.checked)}
            />
            Export all run results
          </label>
          <button type="button" className="btn" onClick={() => void exportSerp()}>
            Export SERP files
          </button>
          <button type="button" className="btn" onClick={() => void exportAvail()}>
            Export availability
          </button>
          <Link className="btn btn-ghost" to="/">
            All projects
          </Link>
        </div>
      </div>

      <div className="tabs">
        {([
          ['domains', 'Domains'],
          ['positions', 'Positions'],
          ['coverage', 'Coverage'],
          ['availability', 'Availability'],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`tab ${tab === id ? 'active' : ''}`}
            onClick={() => {
              setPage(1)
              setTab(id)
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'domains' && (
        <div className="panel">
          <div className="toolbar">
            <div className="field">
              <label>Search (domain / keyword / URL)</label>
              <input
                value={dq}
                onChange={(e) => setDq(e.target.value)}
                placeholder="domain, keyword or URL…"
              />
            </div>
            <div className="field">
              <label>Last seen on/before (UC-03, server-wide)</label>
              <input
                type="date"
                value={lastSeenBefore}
                onChange={(e) => setLastSeenBefore(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    setPage(1)
                    void loadTab('domains', 1)
                  }
                }}
              />
            </div>
            <div className="field">
              <label>Sort</label>
              <select
                value={domSort}
                onChange={(e) => {
                  const next = e.target.value
                  setDomSort(next)
                  if (next === 'best_organic_rank' || next === 'last_seen') setDomOrder('asc')
                  else setDomOrder('desc')
                }}
              >
                <option value="keywords_found">keywords_found</option>
                <option value="best_organic_rank">best_organic_rank</option>
                <option value="last_seen">last_seen</option>
                <option value="countries_found">countries_found</option>
                <option value="months_found">months_found</option>
                <option value="serp_appearances">serp_appearances</option>
                <option value="domain">domain</option>
              </select>
            </div>
            <div className="field">
              <label>Order</label>
              <select value={domOrder} onChange={(e) => setDomOrder(e.target.value)}>
                <option value="desc">desc</option>
                <option value="asc">asc</option>
              </select>
            </div>
            <label className="btn btn-ghost" style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={domainsAvailableOnly}
                onChange={(e) => setDomainsAvailableOnly(e.target.checked)}
              />
              Available (preliminary)
            </label>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setPage(1)
                void loadTab('domains', 1)
              }}
            >
              Apply
            </button>
            <button type="button" className="btn" onClick={() => void estimateAvail()}>
              Availability estimate
            </button>
            <button type="button" className="btn btn-primary" onClick={() => void startAvail('all_unique')}>
              Check all unique
            </button>
            <button type="button" className="btn" onClick={() => void startAvail('filtered')}>
              Check selected ({selected.size})
            </button>
            <button type="button" className="btn" onClick={() => void startAvail('filtered', true)}>
              Recheck selected
            </button>
          </div>
          {availEst && <div className="banner banner-info">{availEst}</div>}
          <div className="hint" style={{ marginBottom: '0.5rem' }}>
            Available (preliminary) is not a purchase guarantee — UNKNOWN / ERROR / RESTRICTED are never
            treated as free. Eligibility (e.g. .com.au) is separate. Last-seen (UC-03) is filtered on the
            server across the whole run; pager total is the filtered count, not the current page.
          </div>
          <DomainTable
            rows={domains?.items || []}
            selected={selected}
            onToggle={toggleSel}
            onOpen={openCard}
          />
          <Pager
            page={page}
            total={domains?.total || 0}
            pageSize={50}
            onChange={(p) => setPage(p)}
          />
        </div>
      )}

      {tab === 'positions' && (
        <div className="panel">
          <div className="toolbar">
            <div className="field">
              <label>Keyword</label>
              <input value={posKw} onChange={(e) => setPosKw(e.target.value)} />
            </div>
            <div className="field">
              <label>Domain</label>
              <input value={posDomain} onChange={(e) => setPosDomain(e.target.value)} />
            </div>
            <div className="field">
              <label>Country</label>
              <select value={posLoc} onChange={(e) => setPosLoc(e.target.value)}>
                <option value="">All</option>
                {(positions?.facets?.locations || []).map((l) => (
                  <option key={l.location_code} value={String(l.location_code)}>
                    {l.location_name || l.location_code}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Language</label>
              <select value={posLang} onChange={(e) => setPosLang(e.target.value)}>
                <option value="">All</option>
                {(positions?.facets?.languages || []).map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Month</label>
              <select value={posMonth} onChange={(e) => setPosMonth(e.target.value)}>
                <option value="">All</option>
                {(positions?.facets?.months || []).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Rank ≤</label>
              <select value={posRankMax} onChange={(e) => setPosRankMax(e.target.value)}>
                <option value="">Any</option>
                {(positions?.facets?.rank_presets || [3, 10, 20, 50, 100]).map((n) => (
                  <option key={n} value={String(n)}>
                    1–{n}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>TLD</label>
              <input value={posTld} onChange={(e) => setPosTld(e.target.value)} placeholder="com.au" />
            </div>
            <div className="field">
              <label>Source</label>
              <select value={posSource} onChange={(e) => setPosSource(e.target.value)}>
                <option value="">All</option>
                {(positions?.facets?.sources || []).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setPage(1)
                void loadTab('positions', 1)
              }}
            >
              Apply
            </button>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Keyword</th>
                  <th>Country</th>
                  <th>Lang</th>
                  <th>Observed</th>
                  <th>Month</th>
                  <th>Rank</th>
                  <th>Abs</th>
                  <th>Domain</th>
                  <th>URL</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {(positions?.items || []).map((r, i) => (
                  <tr key={i}>
                    <td>{r.keyword}</td>
                    <td>{r.location_name || r.location_code}</td>
                    <td>{r.language}</td>
                    <td className="mono">{r.observed_at?.slice(0, 19)}</td>
                    <td className="mono">{r.month}</td>
                    <td className="mono">{r.organic_rank}</td>
                    <td className="mono">{r.absolute_rank}</td>
                    <td className="mono linkish" onClick={() => r.domain && void openCard(r.domain)}>
                      {r.domain}
                    </td>
                    <td className="mono">{r.url}</td>
                    <td className="mono">{r.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} total={positions?.total || 0} pageSize={50} onChange={setPage} />
        </div>
      )}

      {tab === 'coverage' && (
        <div className="panel">
          <div className="banner banner-warn">
            Coverage matrix (keyword × country × month). Missing cells are archive gaps — not zero ranking.
          </div>
          {coverageMatrix?.stats && (
            <div className="banner banner-info">
              Planned cells {coverageMatrix.stats.planned_snapshots} · AVAILABLE{' '}
              {coverageMatrix.stats.available_snapshots}
              {Object.entries(coverageMatrix.stats.status_counts || {})
                .map(([k, v]) => ` · ${k} ${v}`)
                .join('')}
            </div>
          )}
          <div className="toolbar">
            <div className="field">
              <label>Keyword</label>
              <input value={covKw} onChange={(e) => setCovKw(e.target.value)} placeholder="contains…" />
            </div>
            <div className="field">
              <label>Country</label>
              <select value={covLoc} onChange={(e) => setCovLoc(e.target.value)}>
                <option value="">All</option>
                {(coverageMatrix?.locations || []).map((l) => (
                  <option key={l.location_code} value={String(l.location_code)}>
                    {l.location_name || l.location_code}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Status</label>
              <select value={covStatus} onChange={(e) => setCovStatus(e.target.value)}>
                <option value="">All</option>
                <option value="AVAILABLE">AVAILABLE</option>
                <option value="NO_SNAPSHOT">NO_SNAPSHOT</option>
                <option value="PARTIAL_DEPTH">PARTIAL_DEPTH</option>
                <option value="API_ERROR">API_ERROR</option>
                <option value="NOT_REQUESTED">NOT_REQUESTED</option>
              </select>
            </div>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setPage(1)
                void loadTab('coverage', 1)
              }}
            >
              Apply
            </button>
          </div>
          {(coverageMatrix?.blocks || []).map((block) => (
            <div key={block.keyword} style={{ marginBottom: '1.25rem' }}>
              <h3 style={{ margin: '0.75rem 0 0.35rem' }}>{block.keyword}</h3>
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Country</th>
                      {(coverageMatrix?.months || []).map((m) => (
                        <th key={m} className="mono">
                          {m}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row) => (
                      <tr key={`${block.keyword}-${row.location_code}`}>
                        <td>{row.location_name || row.location_code}</td>
                        {(coverageMatrix?.months || []).map((m) => {
                          const st = row.cells[m]
                          return (
                            <td key={m}>
                              {st ? <StatusBadge status={st} /> : <span className="hint">—</span>}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          {!coverageMatrix?.blocks?.length && (
            <div className="empty">No coverage rows yet — finish SERP run first.</div>
          )}
          <Pager
            page={page}
            total={coverageMatrix?.keyword_total || 0}
            pageSize={coverageMatrix?.keyword_page_size || 15}
            onChange={setPage}
          />
        </div>
      )}

      {tab === 'availability' && (
        <div className="panel">
          <div className="toolbar">
            <div className="field">
              <label>Budget credits</label>
              <input value={availBudget} onChange={(e) => setAvailBudget(e.target.value)} />
            </div>
            <label className="hint" style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
              <input type="checkbox" checked={availOnly} onChange={(e) => setAvailOnly(e.target.checked)} />
              Available only (preliminary/confirmed)
            </label>
            <button type="button" className="btn" onClick={() => void estimateAvail()}>
              Estimate
            </button>
            <button type="button" className="btn btn-primary" onClick={() => void startAvail('all_unique')}>
              Check availability
            </button>
            <button type="button" className="btn" onClick={() => void exportAvail()}>
              Export
            </button>
            {job && job.status === 'RUNNING' && (
              <>
                <button
                  type="button"
                  className="btn"
                  onClick={() => void api.post(`/api/availability/jobs/${job.job_id}/pause`)}
                >
                  Pause job
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={() => void api.post(`/api/availability/jobs/${job.job_id}/cancel`)}
                >
                  Stop job
                </button>
              </>
            )}
            {job && job.status === 'PAUSED' && (
              <button
                type="button"
                className="btn"
                onClick={() => void api.post(`/api/availability/jobs/${job.job_id}/resume`)}
              >
                Resume job
              </button>
            )}
          </div>
          {availEst && <div className="banner banner-info">{availEst}</div>}
          {job && (
            <div className="stats" style={{ marginBottom: '0.75rem' }}>
              <span className="stat">
                job <b>{job.status}</b>
              </span>
              <span className="stat">
                credits <b>
                  {job.spent_credits}/{job.budget_cap_credits}
                </b>
              </span>
              {Object.entries(job.items_by_status || {}).map(([k, v]) => (
                <span className="stat" key={k}>
                  {k} <b>{v}</b>
                </span>
              ))}
            </div>
          )}
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Domain</th>
                  <th>Registration</th>
                  <th>Eligibility</th>
                  <th>Best rank</th>
                  <th>Checked</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(availability?.items || []).map((r) => (
                  <tr key={r.domain}>
                    <td className="mono linkish" onClick={() => void openCard(r.domain)}>
                      {r.domain}
                    </td>
                    <td>
                      <StatusBadge status={r.registration_status || '—'} />
                    </td>
                    <td>
                      <StatusBadge status={r.eligibility_status || '—'} />
                    </td>
                    <td className="mono">{r.best_organic_rank}</td>
                    <td className="mono">{r.last_checked_at?.slice(0, 19) || '—'}</td>
                    <td>
                      <button type="button" className="btn btn-ghost" onClick={() => void recheck(r.domain)}>
                        Recheck
                      </button>
                      <button type="button" className="btn btn-ghost" onClick={() => void confirmLive(r.domain)}>
                        Confirm live
                      </button>
                      <a
                        href={`https://www.godaddy.com/domainsearch/find?domainToCheck=${encodeURIComponent(r.domain)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Registrar
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} total={availability?.total || 0} pageSize={50} onChange={setPage} />
        </div>
      )}

      {cardDomain && card && (
        <DomainCardModal
          domain={cardDomain}
          card={card}
          onClose={() => {
            setCardDomain(null)
            setCard(null)
          }}
          onRecheck={() => void recheck(cardDomain)}
          onConfirm={() => void confirmLive(cardDomain)}
        />
      )}
    </Layout>
  )
}

function DomainTable({
  rows,
  selected,
  onToggle,
  onOpen,
}: {
  rows: DomainRow[]
  selected: Set<string>
  onToggle: (d: string) => void
  onOpen: (d: string) => void
}) {
  if (!rows.length) return <div className="empty">No domains yet (check Coverage if SERP finished empty).</div>
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th />
            <th>Domain</th>
            <th>Keywords</th>
            <th>Countries</th>
            <th>Months</th>
            <th>Hits</th>
            <th>Best rank</th>
            <th>First seen</th>
            <th>Last seen</th>
            <th>Best KW</th>
            <th>Reg. status</th>
            <th>Provider</th>
            <th>Checked</th>
            <th>Age</th>
            <th>Restrictions</th>
            <th>Confirm</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.domain}>
              <td>
                <input type="checkbox" checked={selected.has(r.domain)} onChange={() => onToggle(r.domain)} />
              </td>
              <td className="mono linkish" onClick={() => onOpen(r.domain)}>
                {r.domain}
              </td>
              <td className="mono">{r.keywords_found}</td>
              <td className="mono">{r.countries_found}</td>
              <td className="mono">{r.months_found}</td>
              <td className="mono">{r.serp_appearances}</td>
              <td className="mono">{r.best_organic_rank}</td>
              <td className="mono">{r.first_seen?.slice(0, 10)}</td>
              <td className="mono">{r.last_seen?.slice(0, 10)}</td>
              <td>{r.best_rank_keyword}</td>
              <td>
                <StatusBadge status={r.registration_status || 'NOT_CHECKED'} />
              </td>
              <td className="mono">{r.availability_provider || '—'}</td>
              <td className="mono">{r.last_checked_at?.slice(0, 19) || '—'}</td>
              <td className="mono">{r.check_age || '—'}</td>
              <td className="mono">{r.registration_restrictions || r.eligibility_status || '—'}</td>
              <td className="mono">{r.confirmation_status || 'NONE'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Pager({
  page,
  total,
  pageSize,
  onChange,
}: {
  page: number
  total: number
  pageSize: number
  onChange: (p: number) => void
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="pager">
      <button type="button" className="btn" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        Prev
      </button>
      <span>
        Page {page} / {pages} · {total} rows
      </span>
      <button type="button" className="btn" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        Next
      </button>
    </div>
  )
}

function DomainCardModal({
  domain,
  card,
  onClose,
  onRecheck,
  onConfirm,
}: {
  domain: string
  card: Record<string, unknown>
  onClose: () => void
  onRecheck: () => void
  onConfirm: () => void
}) {
  const months = (card.months as { month: string; best_rank: number | null; appearances: number }[]) || []
  const kws = (card.keywords as { keyword: string; best_rank: number | null; countries: number }[]) || []
  const regions =
    (card.regions as {
      location_code: number
      location_name: string | null
      language: string
      best_rank: number | null
      appearances: number
    }[]) || []
  const history =
    (card.check_history as {
      checked_at: string | null
      provider: string
      status: string
      eligibility_status: string
      raw_availability: string | null
      raw_error: string | null
    }[]) || []
  const urls = (card.historical_urls as string[]) || []
  const avail = (card.availability as {
    registration_status?: string
    eligibility_status?: string
    provider?: string | null
    last_checked_at?: string | null
    check_age?: string | null
    confirmation_status?: string
    cctld_warning?: {
      suffix?: string | null
      eligibility_type?: string
      restricted?: boolean
      policy_url?: string | null
      message?: string
    } | null
  }) || {}
  const note = typeof card.note === 'string' ? card.note : 'Known months only — gaps are not filled with zeros.'
  const warn = avail.cctld_warning

  async function copyUrls() {
    const text = urls.join('\n')
    if (!text) return
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <h2>{domain}</h2>
            <p className="hint">{note}</p>
          </div>
          <button type="button" className="btn" onClick={onClose}>
            Close
          </button>
        </header>

        <h3>Availability</h3>
        <div className="toolbar" style={{ flexWrap: 'wrap', gap: '0.75rem' }}>
          <span>
            Status <StatusBadge status={avail.registration_status || 'NOT_CHECKED'} />
          </span>
          <span className="mono">Provider {avail.provider || '—'}</span>
          <span className="mono">Checked {avail.last_checked_at?.slice(0, 19) || '—'}</span>
          <span className="mono">Age {avail.check_age || '—'}</span>
          <span className="mono">Eligibility {avail.eligibility_status || '—'}</span>
          <span className="mono">Confirm {avail.confirmation_status || 'NONE'}</span>
        </div>
        {warn?.message && (
          <div className="banner banner-warn">
            {warn.message}
            {warn.policy_url ? (
              <>
                {' '}
                <a href={warn.policy_url} target="_blank" rel="noreferrer">
                  Policy
                </a>
              </>
            ) : null}
          </div>
        )}

        <div className="toolbar">
          <button type="button" className="btn btn-primary" onClick={onRecheck}>
            Verify now
          </button>
          <button type="button" className="btn" onClick={onConfirm}>
            Confirm live
          </button>
          <a
            className="btn"
            href={`https://www.godaddy.com/domainsearch/find?domainToCheck=${encodeURIComponent(domain)}`}
            target="_blank"
            rel="noreferrer"
          >
            Open registrar
          </a>
          <button type="button" className="btn" onClick={() => void copyUrls()} disabled={!urls.length}>
            Copy historical URLs
          </button>
        </div>

        <h3 style={{ marginTop: '1rem' }}>Check history</h3>
        {history.length ? (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Checked at</th>
                  <th>Provider</th>
                  <th>Status</th>
                  <th>Eligibility</th>
                  <th>Raw</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h, i) => (
                  <tr key={`${h.checked_at}-${i}`}>
                    <td className="mono">{h.checked_at?.slice(0, 19) || '—'}</td>
                    <td className="mono">{h.provider}</td>
                    <td>
                      <StatusBadge status={h.status} />
                    </td>
                    <td className="mono">{h.eligibility_status}</td>
                    <td className="mono">{h.raw_availability || '—'}</td>
                    <td className="mono">{h.raw_error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">No availability checks yet — use Verify now.</div>
        )}

        <h3 style={{ marginTop: '1rem' }}>Keywords</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Keyword</th>
                <th>Best rank</th>
                <th>Countries</th>
              </tr>
            </thead>
            <tbody>
              {kws.map((k) => (
                <tr key={k.keyword}>
                  <td>{k.keyword}</td>
                  <td className="mono">{k.best_rank}</td>
                  <td className="mono">{k.countries}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 style={{ marginTop: '1rem' }}>Best by region</h3>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Country</th>
                <th>Lang</th>
                <th>Best rank</th>
                <th>Appearances</th>
              </tr>
            </thead>
            <tbody>
              {regions.map((r) => (
                <tr key={`${r.location_code}-${r.language}`}>
                  <td>{r.location_name || r.location_code}</td>
                  <td>{r.language}</td>
                  <td className="mono">{r.best_rank}</td>
                  <td className="mono">{r.appearances}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 style={{ marginTop: '1rem' }}>Monthly history</h3>
        <p className="hint">Only months with known SERP hits — missing months are not filled with zeros.</p>
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Month</th>
                <th>Best rank</th>
                <th>Appearances</th>
              </tr>
            </thead>
            <tbody>
              {months.map((m) => (
                <tr key={m.month}>
                  <td className="mono">{m.month}</td>
                  <td className="mono">{m.best_rank}</td>
                  <td className="mono">{m.appearances}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {urls.length > 0 && (
          <>
            <h3 style={{ marginTop: '1rem' }}>Historical URLs</h3>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>URL</th>
                  </tr>
                </thead>
                <tbody>
                  {urls.slice(0, 50).map((u) => (
                    <tr key={u}>
                      <td className="mono">{u}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
