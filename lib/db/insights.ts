/**
 * Generate insights from learning data
 */

import type { 
  PromptStats, 
  SymbolStats, 
  ConfidenceBucket, 
  LearningInsight 
} from '@/types/learning';

export function generateInsights(
  prompts: PromptStats[],
  symbols: SymbolStats[],
  confidenceBuckets: ConfidenceBucket[]
): LearningInsight[] {
  const insights: LearningInsight[] = [];

  // Best performing prompt
  if (prompts.length > 0) {
    const best = prompts[0];
    if (best.win_rate >= 50) {
      insights.push({
        type: 'positive',
        title: `Best Prompt: ${best.prompt_name}`,
        description: `${best.win_rate}% win rate across ${best.total_trades} trades`,
        metric: best.win_rate,
      });
    }
  }

  // Worst performing prompt
  if (prompts.length > 1) {
    const worst = prompts[prompts.length - 1];
    if (worst.win_rate < 40 && worst.total_trades >= 10) {
      insights.push({
        type: 'negative',
        title: `Consider removing: ${worst.prompt_name}`,
        description: `Only ${worst.win_rate}% win rate with ${worst.total_trades} trades`,
        metric: worst.win_rate,
      });
    }
  }

  // Best performing symbol
  const goodSymbols = symbols.filter(s => s.win_rate >= 55 && s.total_trades >= 5);
  if (goodSymbols.length > 0) {
    const best = goodSymbols[0];
    insights.push({
      type: 'positive',
      title: `Strong on ${best.symbol}`,
      description: `${best.win_rate}% win rate, consider increasing allocation`,
      metric: best.win_rate,
    });
  }

  // Weak symbols
  const weakSymbols = symbols.filter(s => s.win_rate < 40 && s.total_trades >= 5);
  if (weakSymbols.length > 0) {
    insights.push({
      type: 'negative',
      title: `Weak symbols detected`,
      description: `${weakSymbols.map(s => s.symbol).join(', ')} have < 40% win rate`,
    });
  }

  // Confidence correlation
  if (confidenceBuckets.length >= 3) {
    const highConf = confidenceBuckets.filter(b => b.bucket >= 0.7);
    const lowConf = confidenceBuckets.filter(b => b.bucket <= 0.3);
    
    const highConfWinRate = highConf.reduce((sum, b) => sum + b.wins, 0) / 
      Math.max(1, highConf.reduce((sum, b) => sum + b.trades, 0)) * 100;
    const lowConfWinRate = lowConf.reduce((sum, b) => sum + b.wins, 0) / 
      Math.max(1, lowConf.reduce((sum, b) => sum + b.trades, 0)) * 100;

    if (highConfWinRate > lowConfWinRate + 10) {
      insights.push({
        type: 'positive',
        title: 'Confidence is predictive',
        description: `High confidence trades: ${highConfWinRate.toFixed(0)}% vs low: ${lowConfWinRate.toFixed(0)}%`,
        metric: highConfWinRate - lowConfWinRate,
      });
    } else if (highConfWinRate < lowConfWinRate) {
      insights.push({
        type: 'negative',
        title: 'Confidence not predictive',
        description: 'High confidence trades perform worse - recalibration needed',
      });
    }
  }

  // Total trades insight
  const totalTrades = prompts.reduce((sum, p) => sum + p.total_trades, 0);
  if (totalTrades < 50) {
    insights.push({
      type: 'neutral',
      title: 'Limited data',
      description: `Only ${totalTrades} trades analyzed - results may not be statistically significant`,
      metric: totalTrades,
    });
  } else if (totalTrades >= 200) {
    insights.push({
      type: 'positive',
      title: 'Robust dataset',
      description: `${totalTrades} trades provide statistically significant results`,
      metric: totalTrades,
    });
  }

  return insights;
}

