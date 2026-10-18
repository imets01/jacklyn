import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { api } from './client'
import type {
  AccountCreate,
  AccountSummary,
  ChartRange,
  ChartResponse,
  ColumnMappingConfig,
  HistoryRange,
  HealthReport,
  HistoryResponse,
  HoldingDetail,
  InvestorProfile,
  HoldingsResponse,
  IbkrConnection,
  IbkrConnectionIn,
  ImportCommitRequest,
  ImportCommitResult,
  ImportLog,
  ImportPreview,
  MarketRefreshResult,
  PortfolioSummary,
  SavedMapping,
  TransactionPage,
  TransactionType,
  User,
} from './types'

export const queryKeys = {
  me: ['me'] as const,
  summary: (base: string) => ['summary', base] as const,
  history: (base: string, range: HistoryRange, accountId?: number) => ['history', base, range, accountId ?? 'all'] as const,
  holdings: (base: string, accountId?: number) => ['holdings', base, accountId ?? 'all'] as const,
  holding: (base: string, assetId: number) => ['holding', base, assetId] as const,
  chart: (assetId: number, range: ChartRange) => ['chart', assetId, range] as const,
  accounts: (base: string) => ['accounts', base] as const,
  account: (base: string, id: number) => ['account', base, id] as const,
  transactions: (filters: TransactionFilters, page: number) => ['transactions', filters, page] as const,
  importLogs: ['import-logs'] as const,
  mappings: ['mappings'] as const,
  ibkr: ['ibkr-sync'] as const,
}

/** Everything that depends on ledger contents; invalidated after an import or account change. */
const LEDGER_KEYS = ['summary', 'history', 'holdings', 'holding', 'accounts', 'account', 'transactions', 'import-logs', 'health']

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

export function useHoldingDetail(base: string, assetId: number) {
  return useQuery({
    queryKey: queryKeys.holding(base, assetId),
    queryFn: () => api.get<HoldingDetail>(`/api/portfolio/holdings/${assetId}`, { base }),
    placeholderData: keepPreviousData,
  })
}

export function useAssetChart(assetId: number, range: ChartRange) {
  return useQuery({
    queryKey: queryKeys.chart(assetId, range),
    queryFn: () => api.get<ChartResponse>(`/api/assets/${assetId}/chart`, { range }),
    placeholderData: keepPreviousData,
    // The server caches Yahoo for 2 minutes (1D) to an hour; match it so switching ranges is instant.
    staleTime: range === '1D' ? 120_000 : 600_000,
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

export interface TransactionFilters {
  accountId?: number | null
  assetId?: number | null
  types?: readonly TransactionType[]
  search?: string
  dateFrom?: string
  dateTo?: string
}

export function useTransactions(filters: TransactionFilters, page: number, pageSize = 50) {
  return useQuery({
    queryKey: queryKeys.transactions(filters, page),
    queryFn: () =>
      api.get<TransactionPage>('/api/transactions', {
        account_id: filters.accountId ?? null,
        asset_id: filters.assetId ?? null,
        type: filters.types?.length ? [...filters.types] : null,
        q: filters.search || null,
        date_from: filters.dateFrom || null,
        date_to: filters.dateTo || null,
        limit: pageSize,
        offset: page * pageSize,
      }),
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

export function useUpdateAccount() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<AccountCreate> }) =>
      api.patch<AccountSummary>(`/api/accounts/${id}`, patch),
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

export function useHealthReport(base: string, amount: string | null, includeCash: boolean) {
  return useQuery({
    queryKey: ['health', base, amount, includeCash] as const,
    queryFn: () => api.get<HealthReport>('/api/health/report', { base, amount, include_cash: includeCash }),
    placeholderData: keepPreviousData,
  })
}

export function useSaveInvestorProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (profile: InvestorProfile) => api.put<InvestorProfile>('/api/health/profile', profile),
    onSuccess: () => client.invalidateQueries({ queryKey: ['health'] }),
  })
}

/** The IBKR Flex connection; polls while a sync runs and refreshes the ledger once it finishes. */
export function useIbkrConnection() {
  const client = useQueryClient()
  const query = useQuery({
    queryKey: queryKeys.ibkr,
    queryFn: () => api.get<IbkrConnection | null>('/api/sync/ibkr'),
    refetchInterval: (current) => (current.state.data?.running ? 2000 : false),
  })
  const running = query.data?.running ?? false
  const wasRunning = useRef(running)
  useEffect(() => {
    if (wasRunning.current && !running) void invalidateLedger(client)
    wasRunning.current = running
  }, [running, client])
  return query
}

export function useSaveIbkrConnection() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (connection: IbkrConnectionIn) => api.put<IbkrConnection>('/api/sync/ibkr', connection),
    onSuccess: (connection) => client.setQueryData(queryKeys.ibkr, connection),
  })
}

export function useDeleteIbkrConnection() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete<null>('/api/sync/ibkr'),
    onSuccess: () => client.setQueryData(queryKeys.ibkr, null),
  })
}

export function useRunIbkrSync() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<IbkrConnection>('/api/sync/ibkr/run'),
    onSuccess: (connection) => {
      client.setQueryData(queryKeys.ibkr, connection)
      if (!connection.running) void invalidateLedger(client)
    },
  })
}
