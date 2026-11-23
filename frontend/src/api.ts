const AUTH_KEY = 'hsdf_basic_auth'

export function getAuthHeader(): string | null {
  return sessionStorage.getItem(AUTH_KEY)
}

export function setAuth(user: string, password: string) {
  sessionStorage.setItem(AUTH_KEY, 'Basic ' + btoa(`${user}:${password}`))
}

export function clearAuth() {
  sessionStorage.removeItem(AUTH_KEY)
}

export function isLoggedIn(): boolean {
  return Boolean(getAuthHeader())
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.status = status
    this.body = body
  }
}

function redirectToLogin() {
  clearAuth()
  if (!window.location.pathname.startsWith('/login')) {
    window.location.assign('/login')
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const auth = getAuthHeader()
  if (auth) headers.set('Authorization', auth)
  // FormData must set its own multipart boundary — do not force JSON Content-Type
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const res = await fetch(path, { ...init, headers })
  const text = await res.text()
  let data: unknown = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (res.status === 401) {
    redirectToLogin()
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? String((data as { detail: unknown }).detail)
        : 'Unauthorized'
    throw new ApiError(401, detail, data)
  }
  if (!res.ok) {
    const detail =
      typeof data === 'object' && data && 'detail' in data
        ? JSON.stringify((data as { detail: unknown }).detail)
        : text || res.statusText
    throw new ApiError(res.status, detail, data)
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
}

export async function downloadAuthenticated(url: string, filename: string) {
  const headers = new Headers()
  const auth = getAuthHeader()
  if (auth) headers.set('Authorization', auth)
  const res = await fetch(url, { headers })
  if (!res.ok) throw new ApiError(res.status, `Download failed: ${res.status}`, null)
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}
