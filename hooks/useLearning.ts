'use client';

import { useState, useEffect, useCallback } from 'react';
import type { LearningData } from '@/types/learning';

interface SummaryStats {
  totalTrades: number;
  totalWins: number;
  overallWinRate: number;
  totalPnl: number;
  uniquePrompts: number;
  uniqueSymbols: number;
}

interface UseLearningResult {
  data: LearningData | null;
  summary: SummaryStats | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useLearning(): UseLearningResult {
  const [data, setData] = useState<LearningData | null>(null);
  const [summary, setSummary] = useState<SummaryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      
      const response = await fetch('/api/learning');
      const result = await response.json();
      
      if (!response.ok) {
        throw new Error(result.message || result.error || 'Failed to fetch');
      }
      
      setData(result.data);
      setSummary(result.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      console.error('useLearning error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    data,
    summary,
    loading,
    error,
    refresh: fetchData,
  };
}

