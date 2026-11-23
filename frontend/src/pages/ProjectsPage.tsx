import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Layout } from '../components/Layout'
import type { ProjectListItem } from '../types'

export function ProjectsPage() {
  const [items, setItems] = useState<ProjectListItem[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function load(query = q) {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<{ total: number; items: ProjectListItem[] }>(
        `/api/projects?page_size=50${query ? `&q=${encodeURIComponent(query)}` : ''}`,
      )
      setItems(data.items)
      setTotal(data.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load('')
  }, [])

  return (
    <Layout>
      <div className="panel">
        <div className="toolbar" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Projects</h2>
          <div className="toolbar">
            <div className="field">
              <label htmlFor="pq">Search</label>
              <input
                id="pq"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && void load()}
                placeholder="Name…"
              />
            </div>
            <button type="button" className="btn" onClick={() => void load()}>
              Search
            </button>
            <Link className="btn btn-primary" to="/new">
              New project
            </Link>
          </div>
        </div>
        {error && <div className="banner banner-error">{error}</div>}
        {loading ? (
          <div className="empty">Loading…</div>
        ) : items.length === 0 ? (
          <div className="empty">No projects yet. Create one to start a SERP run.</div>
        ) : (
          <>
            <p className="hint">{total} project(s)</p>
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Keywords</th>
                    <th>Targets</th>
                    <th>Runs</th>
                    <th>Created</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.map((p) => (
                    <tr key={p.id}>
                      <td>{p.name}</td>
                      <td className="mono">{p.keywords}</td>
                      <td className="mono">{p.targets}</td>
                      <td className="mono">{p.runs}</td>
                      <td className="mono">{p.created_at?.slice(0, 19) || '—'}</td>
                      <td>
                        <Link to={`/projects/${p.id}`}>Open</Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Layout>
  )
}
