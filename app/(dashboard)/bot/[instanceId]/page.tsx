'use client'

import BotDashboard from '@/components/BotDashboard'

interface PageProps {
  params: { instanceId: string }
}

export default function InstanceDetailPage({ params }: PageProps) {
  return <BotDashboard initialInstanceId={params.instanceId} />
}

