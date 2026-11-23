import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, clearAuth, getAuthHeader, setAuth } from '../api'

export function LoginPage() {
  const nav = useNavigate()
  const [user, setUser] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(Boolean(getAuthHeader()))

  // Re-validate stored Basic header; never trust sessionStorage alone.
  useEffect(() => {
    if (!getAuthHeader()) {
      setChecking(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        await api.get('/api/meta/serp-window')
        if (!cancelled) nav('/', { replace: true })
      } catch {
        clearAuth()
        if (!cancelled) setChecking(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [nav])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setAuth(user.trim(), password.trim())
    try {
      await api.get('/api/meta/serp-window')
      nav('/', { replace: true })
    } catch (err) {
      clearAuth()
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  if (checking) {
    return (
      <div className="login-wrap">
        <div className="login-card">
          <h1>Historical SERP Domain Finder</h1>
          <p>Checking session…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={onSubmit}>
        <h1>Historical SERP Domain Finder</h1>
        <p>
          Username <code>admin</code>. Password = <code>APP_BASIC_PASSWORD</code> from{" "}
          <code>deploy/vps_bootstrap_credentials.txt</code> (paste it; ignore browser autofill).
        </p>
        {error && (
          <div className="banner banner-error">
            {error === "Unauthorized" || error === "Invalid credentials"
              ? "Wrong password (often Chrome autofill). Paste APP_BASIC_PASSWORD from the credentials file."
              : error}
          </div>
        )}
        <div className="field">
          <label htmlFor="user">Username</label>
          <input
            id="user"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            autoComplete="off"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="pass">Password</label>
          <input
            id="pass"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <button className="btn btn-primary" type="submit" disabled={busy} style={{ width: '100%' }}>
          {busy ? 'Checking…' : 'Enter'}
        </button>
      </form>
    </div>
  )
}
