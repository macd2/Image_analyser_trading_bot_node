'use client'

import { Suspense } from 'react'
import { SimulatorPage } from '@/components/SimulatorPage'
import { LoadingState } from '@/components/shared'

export default function SimulatorPageWrapper() {
  return (
    <Suspense fallback={<LoadingState />}>
      <SimulatorPage />
    </Suspense>
  )
}

