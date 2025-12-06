import { LucideIcon } from 'lucide-react'

interface StatCardProps {
  label: string
  value: string
  change: string
  icon: LucideIcon
  positive: boolean
}

export default function StatCard({
  label,
  value,
  change,
  icon: Icon,
  positive,
}: StatCardProps) {
  return (
    <div className="card">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-slate-400 text-sm">{label}</p>
          <p className="text-2xl font-bold text-white mt-2">{value}</p>
          <p className={`text-xs mt-2 ${positive ? 'text-green-400' : 'text-red-400'}`}>
            {change}
          </p>
        </div>
        <div className={`p-3 rounded-lg ${positive ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
          <Icon size={24} className={positive ? 'text-green-400' : 'text-red-400'} />
        </div>
      </div>
    </div>
  )
}

