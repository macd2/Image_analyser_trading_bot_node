'use client'

import { InstancePage } from '@/components/instance'

interface PageProps {
  params: { id: string }
}

export default function InstanceDetailPage({ params }: PageProps) {
  return <InstancePage instanceId={params.id} />
}

