export class ApiError extends Error {
  readonly status: number
  /** Machine-readable reason when the API provides one (e.g. "totp_required"). */
  readonly code: string | null

  constructor(status: number, message: string, code: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

/** Fired when the server says the session is gone, so the app can drop back to the sign-in screen. */
export const UNAUTHORIZED_EVENT = 'jacklyn:unauthorized'

interface FastApiValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

function describeError(body: unknown, fallback: string): { message: string; code: string | null } {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return { message: detail, code: null }
    if (Array.isArray(detail)) {
      const message = (detail as FastApiValidationIssue[])
        .map((issue) => {
          const field = issue.loc?.filter((part) => part !== 'body').join('.')
          const text = (issue.msg ?? 'invalid').replace(/^Value error, /, '')
          return field ? `${field}: ${text}` : text
        })
        .join('; ')
      return { message, code: null }
    }
    if (detail && typeof detail === 'object') {
      const { message, code } = detail as { message?: unknown; code?: unknown }
      return {
        message: typeof message === 'string' ? message : fallback,
        code: typeof code === 'string' ? code : null,
      }
    }
  }
  return { message: fallback, code: null }
}

type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>

function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined) continue
    if (Array.isArray(value)) value.forEach((item) => params.append(key, String(item)))
    else params.set(key, String(value))
  }
  const search = params.toString()
  return search ? `${path}?${search}` : path
}

async function request<T>(method: string, path: string, init: { query?: Query; json?: unknown; form?: FormData } = {}): Promise<T> {
  // The custom header is the API's CSRF check: cross-site forms can't send it.
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Jacklyn-Request': '1' }
  let body: BodyInit | undefined
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(init.json)
  } else if (init.form) {
    body = init.form
  }
  const response = await fetch(withQuery(path, init.query), { method, headers, body, credentials: 'same-origin' })
  if (response.status === 204) return undefined as T
  const text = await response.text()
  let parsed: unknown = undefined
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = text
    }
  }
  if (!response.ok) {
    const { message, code } = describeError(parsed, `${response.status} ${response.statusText}`)
    if (response.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(response.status, message, code)
  }
  return parsed as T
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, json?: unknown) => request<T>('POST', path, { json }),
  patch: <T>(path: string, json: unknown) => request<T>('PATCH', path, { json }),
  delete: <T>(path: string) => request<T>('DELETE', path),
  upload: <T>(path: string, form: FormData) => request<T>('POST', path, { form }),
}
