import type {
  Account,
  AccountCreate,
  BaseCurrency,
  ColumnMapping,
  ImportCommit,
  ImportLog,
  ImportOptions,
  ImportPreview,
  Performance,
  PerformanceRange,
  PortfolioSummary,
  SavedMapping,
  User,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === "object" && d && "msg" in d ? String(d.msg) : String(d)))
      .join("; ");
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Can't reach the Jacklyn API. Is the backend running?");
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === "object" && "detail" in body) message = describe(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

const json = (body: unknown, method = "POST"): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export interface ImportParams {
  file: File;
  accountId: number;
  parser?: string;
  mapping?: ColumnMapping | null;
  mappingId?: number | null;
}

function importForm(p: ImportParams, extra: Record<string, string | null | undefined> = {}) {
  const form = new FormData();
  form.append("file", p.file);
  form.append("account_id", String(p.accountId));
  form.append("parser", p.mapping ? "generic" : (p.parser ?? "auto"));
  if (p.mapping) form.append("mapping", JSON.stringify(p.mapping));
  if (p.mappingId != null) form.append("mapping_id", String(p.mappingId));
  for (const [k, v] of Object.entries(extra)) if (v) form.append(k, v);
  return form;
}

export const api = {
  me: () => request<User>("/me"),
  summary: (base: BaseCurrency) =>
    request<PortfolioSummary>(`/portfolio/summary?base_currency=${base}`),
  performance: (base: BaseCurrency, range: PerformanceRange) =>
    request<Performance>(`/portfolio/performance?base_currency=${base}&range=${range}`),
  accounts: () => request<Account[]>("/accounts"),
  createAccount: (body: AccountCreate) => request<Account>("/accounts", json(body)),
  importOptions: () => request<ImportOptions>("/import/options"),
  importLogs: () => request<ImportLog[]>("/import/logs"),
  mappings: () => request<SavedMapping[]>("/import/mappings"),
  deleteMapping: (id: number) =>
    request<void>(`/import/mappings/${id}`, { method: "DELETE" }),
  preview: (p: ImportParams) =>
    request<ImportPreview>("/import/preview", { method: "POST", body: importForm(p) }),
  commit: (p: ImportParams & { expectedSha256?: string; saveMappingAs?: string | null }) =>
    request<ImportCommit>("/import/commit", {
      method: "POST",
      body: importForm(p, {
        expected_sha256: p.expectedSha256,
        save_mapping_as: p.saveMappingAs?.trim() || null,
      }),
    }),
};
