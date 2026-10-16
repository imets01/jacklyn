export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface FastApiValidationIssue {
  loc?: (string | number)[]
  msg?: string
}

function describeError(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return (detail as FastApiValidationIssue[])
        .map((issue) => {
          const field = issue.loc?.filter((part) => part !== 'body').join('.')
          return field ? `${field}: ${issue.msg ?? 'invalid'}` : (issue.msg ?? 'invalid')
        })
        .join('; ')
    }
  }
  return fallback
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
  const headers: Record<string, string> = { Accept: 'application/json' }
  let body: BodyInit | undefined
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(init.json)
  } else if (init.form) {
    body = init.form
  }
  const response = await fetch(withQuery(path, init.query), { method, headers, body })
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
    throw new ApiError(response.status, describeError(parsed, `${response.status} ${response.statusText}`))
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
