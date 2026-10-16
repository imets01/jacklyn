import { Link } from 'react-router'

export function NotFound() {
  return (
    <div className="py-24 text-center">
      <p className="font-display text-2xl font-bold">Nothing grows here.</p>
      <Link to="/" className="mt-3 inline-block text-sm font-medium text-accent hover:underline">
        Back to the dashboard
      </Link>
    </div>
  )
}
