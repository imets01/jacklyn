import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { ISODateTime } from './types'

export interface Me {
  id: number
  email: string
  display_name: string
  base_currency: string
  is_admin: boolean
  totp_enabled: boolean
}

export interface SessionStatus {
  authenticated: boolean
  needs_setup: boolean
  user: Me | null
}

export interface LinkInfo {
  purpose: 'invite' | 'password_reset'
  label: string | null
  email: string | null
  expires_at: ISODateTime
}

export interface SignInSession {
  id: number
  created_at: ISODateTime
  last_seen_at: ISODateTime
  expires_at: ISODateTime
  ip_address: string | null
  user_agent: string | null
  current: boolean
}

export interface TotpSetup {
  secret: string
  otpauth_uri: string
  qr_data_url: string
}

export interface AdminUser {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  is_active: boolean
  totp_enabled: boolean
  has_password: boolean
  created_at: ISODateTime
  last_login_at: ISODateTime | null
  account_count: number
}

export interface Invite {
  id: number
  label: string | null
  grants_admin: boolean
  created_at: ISODateTime
  expires_at: ISODateTime
  state: 'pending' | 'used' | 'expired' | 'revoked'
  used_by: string | null
}

export interface CreatedLink {
  path: string
  expires_at: ISODateTime
}

export const authKeys = {
  session: ['auth', 'session'] as const,
  sessions: ['auth', 'sessions'] as const,
  users: ['admin', 'users'] as const,
  invites: ['admin', 'invites'] as const,
}

export function useSession() {
  return useQuery({
    queryKey: authKeys.session,
    queryFn: () => api.get<SessionStatus>('/api/auth/session'),
    staleTime: 60_000,
    retry: 1,
  })
}

/** After signing in/out the cached data belongs to someone else: drop everything, then reload the session. */
function useResetAfterAuthChange() {
  const client = useQueryClient()
  return async () => {
    client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
    await client.invalidateQueries({ queryKey: authKeys.session })
  }
}

export function useLogin() {
  const reset = useResetAfterAuthChange()
  return useMutation({
    mutationFn: (body: { email: string; password: string; totp_code?: string | null }) => api.post<Me>('/api/auth/login', body),
    onSuccess: reset,
  })
}

export function useLogout() {
  const reset = useResetAfterAuthChange()
  return useMutation({ mutationFn: () => api.post<void>('/api/auth/logout'), onSettled: reset })
}

export function useSetup() {
  const reset = useResetAfterAuthChange()
  return useMutation({
    mutationFn: (body: { setup_token: string; email: string; display_name: string; password: string; keep_demo_data: boolean }) =>
      api.post<Me>('/api/auth/setup', body),
    onSuccess: reset,
  })
}

export function useLinkInfo(token: string, purpose: LinkInfo['purpose']) {
  return useQuery({
    queryKey: ['auth', 'link', purpose, token],
    queryFn: () => api.get<LinkInfo>(`/api/auth/links/${encodeURIComponent(token)}`, { purpose }),
    retry: false,
  })
}

export function useRegister() {
  const reset = useResetAfterAuthChange()
  return useMutation({
    mutationFn: (body: { token: string; email: string; display_name: string; password: string }) =>
      api.post<Me>('/api/auth/register', body),
    onSuccess: reset,
  })
}

export function useResetPassword() {
  const reset = useResetAfterAuthChange()
  return useMutation({
    mutationFn: (body: { token: string; password: string }) => api.post<Me>('/api/auth/reset', body),
    onSuccess: reset,
  })
}

export function useChangePassword() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) => api.post<void>('/api/auth/password', body),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.sessions }),
  })
}

export function useSignInSessions() {
  return useQuery({ queryKey: authKeys.sessions, queryFn: () => api.get<SignInSession[]>('/api/auth/sessions') })
}

export function useRevokeSession() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number | 'others') =>
      id === 'others' ? api.post<void>('/api/auth/sessions/revoke-others') : api.delete<void>(`/api/auth/sessions/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.sessions }),
  })
}

export function useTotpSetup() {
  return useMutation({ mutationFn: () => api.post<TotpSetup>('/api/auth/totp/setup') })
}

export function useTotpEnable() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => api.post<Me>('/api/auth/totp/enable', { code }),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.session }),
  })
}

export function useTotpDisable() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (password: string) => api.post<Me>('/api/auth/totp/disable', { password }),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.session }),
  })
}

// ---------------------------------------------------------------- admin

export function useAdminUsers(enabled: boolean) {
  return useQuery({ queryKey: authKeys.users, queryFn: () => api.get<AdminUser[]>('/api/admin/users'), enabled })
}

export function useUpdateUser() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number; is_active?: boolean; is_admin?: boolean }) =>
      api.patch<AdminUser>(`/api/admin/users/${id}`, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.users }),
  })
}

export function useCreateResetLink() {
  return useMutation({ mutationFn: (id: number) => api.post<CreatedLink>(`/api/admin/users/${id}/reset-link`) })
}

export function useInvites(enabled: boolean) {
  return useQuery({ queryKey: authKeys.invites, queryFn: () => api.get<Invite[]>('/api/admin/invites'), enabled })
}

export function useCreateInvite() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { label: string | null; grants_admin: boolean; days: number }) => api.post<CreatedLink>('/api/admin/invites', body),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.invites }),
  })
}

export function useRevokeInvite() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/admin/invites/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: authKeys.invites }),
  })
}

// ---------------------------------------------------------------- backups (admin)

export interface Backup {
  name: string
  kind: 'manual' | 'daily' | 'before-restore'
  size: number
  created_at: ISODateTime
}

export interface BackupList {
  /** SQLite; PostgreSQL deployments use pg_dump. */
  supported: boolean
  /** A daily snapshot is kept automatically. */
  automatic: boolean
  folder: string
  backups: Backup[]
}

const backupsKey = ['admin', 'backups'] as const

export function backupDownloadUrl(name: string): string {
  return `/api/admin/backups/${encodeURIComponent(name)}`
}

export function useBackups(enabled: boolean) {
  return useQuery({ queryKey: backupsKey, queryFn: () => api.get<BackupList>('/api/admin/backups'), enabled })
}

export function useCreateBackup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Backup>('/api/admin/backups'),
    onSuccess: () => client.invalidateQueries({ queryKey: backupsKey }),
  })
}

export function useDeleteBackup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.delete<void>(backupDownloadUrl(name)),
    onSuccess: () => client.invalidateQueries({ queryKey: backupsKey }),
  })
}

export function useRestoreBackup() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      form.append('confirm', 'RESTORE')
      return api.upload<{ safety_backup: Backup }>('/api/admin/backups/restore', form)
    },
  })
}
