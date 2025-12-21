'use client'

import { useState, useCallback } from 'react'
import { X } from 'lucide-react'

export interface DashboardFilterState {
  strategy?: string
  timeframe?: string
  symbol?: string
  dateFrom?: string
  dateTo?: string
}

interface DashboardFiltersProps {
  onFilterChange: (filters: DashboardFilterState) => void
  strategies?: string[]
  symbols?: string[]
}

export default function DashboardFilters({ onFilterChange, strategies = [], symbols = [] }: DashboardFiltersProps) {
  const [filters, setFilters] = useState<DashboardFilterState>({})
  const [isOpen, setIsOpen] = useState(false)

  const timeframes = ['1h', '2h', '4h', '1d']

  const handleFilterChange = useCallback(
    (newFilters: DashboardFilterState) => {
      setFilters(newFilters)
      onFilterChange(newFilters)
      // Persist to localStorage
      localStorage.setItem('dashboardFilters', JSON.stringify(newFilters))
    },
    [onFilterChange]
  )

  const handleStrategyChange = (strategy: string) => {
    handleFilterChange({ ...filters, strategy: strategy || undefined })
  }

  const handleTimeframeChange = (timeframe: string) => {
    handleFilterChange({ ...filters, timeframe: timeframe || undefined })
  }

  const handleSymbolChange = (symbol: string) => {
    handleFilterChange({ ...filters, symbol: symbol || undefined })
  }

  const handleDateFromChange = (date: string) => {
    handleFilterChange({ ...filters, dateFrom: date || undefined })
  }

  const handleDateToChange = (date: string) => {
    handleFilterChange({ ...filters, dateTo: date || undefined })
  }

  const handleClearFilters = () => {
    setFilters({})
    onFilterChange({})
    localStorage.removeItem('dashboardFilters')
  }

  const activeFilterCount = Object.values(filters).filter(v => v).length

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Filters</h3>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="text-xs text-gray-400 hover:text-white transition"
        >
          {isOpen ? 'Hide' : 'Show'} {activeFilterCount > 0 && `(${activeFilterCount})`}
        </button>
      </div>

      {isOpen && (
        <div className="space-y-4">
          {/* Strategy Filter */}
          <div>
            <label className="text-xs text-gray-400 block mb-2">Strategy</label>
            <select
              value={filters.strategy || ''}
              onChange={(e) => handleStrategyChange(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">All Strategies</option>
              {strategies.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Timeframe Filter */}
          <div>
            <label className="text-xs text-gray-400 block mb-2">Timeframe</label>
            <select
              value={filters.timeframe || ''}
              onChange={(e) => handleTimeframeChange(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">All Timeframes</option>
              {timeframes.map(tf => (
                <option key={tf} value={tf}>{tf}</option>
              ))}
            </select>
          </div>

          {/* Symbol Filter */}
          <div>
            <label className="text-xs text-gray-400 block mb-2">Symbol</label>
            <select
              value={filters.symbol || ''}
              onChange={(e) => handleSymbolChange(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">All Symbols</option>
              {symbols.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          {/* Date Range */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400 block mb-2">From</label>
              <input
                type="date"
                value={filters.dateFrom || ''}
                onChange={(e) => handleDateFromChange(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-gray-400 block mb-2">To</label>
              <input
                type="date"
                value={filters.dateTo || ''}
                onChange={(e) => handleDateToChange(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {/* Clear Button */}
          {activeFilterCount > 0 && (
            <button
              onClick={handleClearFilters}
              className="w-full flex items-center justify-center gap-2 bg-slate-700 hover:bg-slate-600 text-white text-sm py-2 rounded transition"
            >
              <X className="w-4 h-4" />
              Clear Filters
            </button>
          )}
        </div>
      )}
    </div>
  )
}

