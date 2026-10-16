import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type {
  AccountCreate,
  AccountSummary,
  ColumnMappingConfig,
  HistoryRange,
  HistoryResponse,
  HoldingsResponse,
  ImportCommitRequest,
  ImportCommitResult,
  ImportLog,
  ImportPreview,
  MarketRefreshResult,
  PortfolioSummary,
  SavedMapping,
  TransactionPage,
  User,
} from './types'

export const queryKeys = {
  me: ['me'] as const,
  summary: (base: string) => ['summary', base] as const,
  history: (base: string, range: HistoryRange, accountId?: number) => ['history', base, range, accountId ?? 'all'] as const,
  holdings: (base: string, accountId?: number) => ['holdings', base, accountId ?? 'all'] as const,
  accounts: (base: string) => ['accounts', base] as const,
  account: (base: string, id: number) => ['account', base, id] as const,
  transactions: (id: number, page: number) => ['transactions', id, page] as const,
  importLogs: ['import-logs'] as const,
  mappings: ['mappings'] as const,
}

/** Everything that depends on ledger contents; invalidated after an import or account change. */
const LEDGER_KEYS = ['summary', 'history', 'holdings', 'accounts', 'account', 'transactions', 'import-logs']

export function useMe() {
  return useQuery({ queryKey: queryKeys.me, queryFn: () => api.get<User>('/api/me') })
}

export function useUpdateMe() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: Partial<Pick<User, 'base_currency' | 'display_name'>>) => api.patch<User>('/api/me', patch),
    onSuccess: (user) => {
      client.setQueryData(queryKeys.me, user)
      return client.invalidateQueries({ queryKey: ['auth', 'session'] })
    },
  })
}

export function useSummary(base: string) {
  return useQuery({
    queryKey: queryKeys.summary(base),
    queryFn: () => api.get<PortfolioSummary>('/api/portfolio/summary', { base }),
    placeholderData: keepPreviousData,
    // Quotes refresh server-side on a TTL; poll gently so the dashboard stays live.
    refetchInterval: (query) => (query.state.data?.market.refreshing ? 4_000 : 60_000),
  })
}

export function useHistory(base: string, range: HistoryRange, accountId?: number) {
  return useQuery({
    queryKey: queryKeys.history(base, range, accountId),
    queryFn: () =>
      api.get<HistoryResponse>('/api/portfolio/history', { base, range, account_id: accountId ?? null }),
    placeholderData: keepPreviousData,
  })
}

export function useHoldings(base: string, accountId?: number) {
  return useQuery({
    queryKey: queryKeys.holdings(base, accountId),
    queryFn: () => api.get<HoldingsResponse>('/api/portfolio/holdings', { base, account_id: accountId ?? null }),
    placeholderData: keepPreviousData,
  })
}

export function useAccounts(base: string) {
  return useQuery({
    queryKey: queryKeys.accounts(base),
    queryFn: () => api.get<AccountSummary[]>('/api/accounts', { base }),
    placeholderData: keepPreviousData,
  })
}

export function useAccount(base: string, id: number) {
  return useQuery({
    queryKey: queryKeys.account(base, id),
    queryFn: () => api.get<AccountSummary>(`/api/accounts/${id}`, { base }),
    placeholderData: keepPreviousData,
  })
}

export function useTransactions(accountId: number, page: number, pageSize = 50) {
  return useQuery({
    queryKey: queryKeys.transactions(accountId, page),
    queryFn: () =>
      api.get<TransactionPage>(`/api/accounts/${accountId}/transactions`, { limit: pageSize, offset: page * pageSize }),
    placeholderData: keepPreviousData,
  })
}

function invalidateLedger(client: ReturnType<typeof useQueryClient>) {
  return client.invalidateQueries({ predicate: (query) => LEDGER_KEYS.includes(String(query.queryKey[0])) })
}

export function useCreateAccount() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: AccountCreate) => api.post<AccountSummary>('/api/accounts', payload),
    onSuccess: () => invalidateLedger(client),
  })
}

export function useDeleteAccount() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, confirm }: { id: number; confirm: string }) =>
      api.delete<void>(`/api/accounts/${id}?${new URLSearchParams({ confirm })}`),
    onSuccess: () => invalidateLedger(client),
  })
}

export interface PreviewRequest {
  file: File
  accountId?: number | null
  parserKey?: string | null
  mapping?: ColumnMappingConfig | null
  mappingId?: number | null
}

export function usePreviewImport() {
  return useMutation({
    mutationFn: ({ file, accountId, parserKey, mapping, mappingId }: PreviewRequest) => {
      const form = new FormData()
      form.append('file', file)
      if (accountId != null) form.append('account_id', String(accountId))
      if (parserKey) form.append('parser_key', parserKey)
      if (mapping) form.append('mapping', JSON.stringify(mapping))
      if (mappingId != null) form.append('mapping_id', String(mappingId))
      return api.upload<ImportPreview>('/api/import/preview', form)
    },
  })
}

export function useCommitImport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: ImportCommitRequest) => api.post<ImportCommitResult>('/api/import/commit', payload),
    onSuccess: () => invalidateLedger(client),
  })
}

export function useImportLogs() {
  return useQuery({ queryKey: queryKeys.importLogs, queryFn: () => api.get<ImportLog[]>('/api/import/logs') })
}

export function useMappings() {
  return useQuery({ queryKey: queryKeys.mappings, queryFn: () => api.get<SavedMapping[]>('/api/mappings') })
}

export function useSaveMapping() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name: string; header_signature: string; config: ColumnMappingConfig }) =>
      api.post<SavedMapping>('/api/mappings', payload),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.mappings }),
  })
}

export function useDeleteMapping() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/mappings/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.mappings }),
  })
}

export function useRefreshMarket() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<MarketRefreshResult>('/api/market/refresh'),
    onSuccess: () => {
      // Let the background refresh land, then re-value everything.
      window.setTimeout(() => void invalidateLedger(client), 5_000)
      return client.invalidateQueries({ queryKey: ['summary'] })
    },
  })
}
