import { Link } from 'react-router-dom'
import { clearAuth } from '../api'

type Props = {
  children: React.ReactNode
  note?: string
}

export function Layout({ children, note }: Props) {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <strong>
            <Link to="/" style={{ color: 'inherit', textDecoration: 'none' }}>
              Historical SERP Domain Finder
            </Link>
          </strong>
          <span>{note || 'Internal tool · DataForSEO history ≈ last 365 days'}</span>
        </div>
        <div className="topbar-actions">
          <Link className="btn btn-ghost" to="/">
            Projects
          </Link>
          <Link className="btn btn-primary" to="/new">
            New project
          </Link>
          <button
            type="button"
            className="btn"
            onClick={() => {
              clearAuth()
              window.location.href = '/login'
            }}
          >
            Log out
          </button>
        </div>
      </header>
      {children}
    </div>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const s = (status || '').toUpperCase()
  let cls = 'badge-muted'
  if (['COMPLETED', 'AVAILABLE', 'AVAILABLE_PRELIMINARY', 'AVAILABLE_CONFIRMED', 'CACHED'].includes(s)) {
    cls = 'badge-ok'
  } else if (
    ['RUNNING', 'QUEUED', 'PAUSED', 'PARTIAL_DEPTH', 'NO_SNAPSHOT', 'TAKEN', 'UNAVAILABLE', 'REQUIRES_EVIDENCE'].includes(
      s,
    )
  ) {
    cls = 'badge-warn'
  } else if (['FAILED', 'CANCELED', 'BUDGET_EXCEEDED', 'API_ERROR', 'ERROR', 'INVALID'].includes(s)) {
    cls = 'badge-danger'
  }
  return <span className={`badge ${cls}`}>{status}</span>
}
