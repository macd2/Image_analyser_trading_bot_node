import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-950">
      <div className="text-center">
        <h1 className="text-6xl font-bold text-slate-400 mb-4">404</h1>
        <p className="text-xl text-slate-400 mb-8">Page not found</p>
        <Link
          href="/"
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 inline-block"
        >
          Go back home
        </Link>
      </div>
    </div>
  )
}

