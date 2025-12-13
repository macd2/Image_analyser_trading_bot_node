'use client'

import { useEffect } from 'react'

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-950">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-red-500 mb-4">Something went wrong!</h1>
        <p className="text-slate-400 mb-8">{error.message}</p>
        <button
          onClick={() => reset()}
          className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Try again
        </button>
      </div>
    </div>
  )
}

