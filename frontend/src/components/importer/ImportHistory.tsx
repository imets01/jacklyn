import { History } from "lucide-react";

import type { Account, ImportLog } from "@/lib/types";

import { Card, CardHeader } from "../ui/primitives";

export function ImportHistory({ logs, accounts }: { logs: ImportLog[]; accounts: Account[] }) {
  const accountName = (id: number) => accounts.find((a) => a.id === id)?.name ?? `#${id}`;
  return (
    <Card>
      <CardHeader title="Recent imports" subtitle="Every commit is logged for audit" />
      {logs.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center text-sm text-muted">
          <History className="size-6 text-subtle" aria-hidden />
          No imports yet. Your demo data was seeded on first start.
        </div>
      ) : (
        <ul className="divide-y divide-line">
          {logs.map((log) => (
            <li key={log.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
              <div className="min-w-0">
                <p className="truncate font-medium text-ink">{log.filename}</p>
                <p className="text-xs text-muted">
                  {accountName(log.account_id)} · {log.parser_key} ·{" "}
                  {new Date(log.created_at).toLocaleString("en-GB", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </p>
              </div>
              <p className="tabular text-xs text-muted">
                <span className="font-semibold text-positive">+{log.rows_imported}</span> imported ·{" "}
                {log.rows_duplicate} dup · {log.rows_failed} failed
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
