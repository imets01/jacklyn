import { CircleAlert } from 'lucide-react'

import { Button, Card, EmptyState } from '../components/ui/primitives'

export function QueryError({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <Card>
      <EmptyState icon={<CircleAlert className="size-5" />} title="Couldn't load this view">
        <p>{error.message}</p>
        <p className="mt-1">Is the API running on port 8000?</p>
        {onRetry ? (
          <Button className="mt-4" onClick={onRetry}>
            Try again
          </Button>
        ) : null}
      </EmptyState>
    </Card>
  )
}
