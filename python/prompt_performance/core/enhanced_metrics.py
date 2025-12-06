"""
Enhanced metrics aggregator with statistical significance testing and confidence intervals.
Extends the basic metrics aggregator with advanced statistical analysis.
"""

import logging
from typing import List, Dict, Any, DefaultDict, Optional, Tuple
from collections import defaultdict
from pathlib import Path
import pandas as pd
import numpy as np

from statistical_testing import StatisticalTestingFramework, calculate_profit_factor

logger = logging.getLogger(__name__)

class EnhancedMetricsAggregator:
    """
    Enhanced metrics aggregator with statistical significance testing,
    confidence intervals, and advanced performance analytics.
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            module_dir = Path(__file__).parent.parent
            output_dir = str(module_dir)
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.statistical_framework = StatisticalTestingFramework()
    
    def generate_enhanced_report(self, trade_results: List[Dict[str, Any]], 
                               analysis_type: str = "version") -> Dict[str, Any]:
        """
        Generate comprehensive performance report with statistical analysis.
        
        Args:
            trade_results: List of trade simulation results
            analysis_type: Either "version" or "hash" for prompt analysis
            
        Returns:
            Dictionary containing comprehensive analysis results
        """
        if not trade_results:
            logger.warning("No trade results provided for enhanced analysis")
            return {}
        
        # Group trades by prompt identifier
        prompt_groups = self._group_trades_by_prompt(trade_results, analysis_type)
        
        # Calculate basic metrics for each prompt
        basic_metrics = self._calculate_basic_metrics_by_prompt(prompt_groups)
        
        # Calculate confidence intervals
        confidence_intervals = self._calculate_confidence_intervals_by_prompt(prompt_groups)
        
        # Perform statistical comparisons
        statistical_comparisons = self.statistical_framework.perform_multiple_comparisons(prompt_groups)
        
        # Generate statistical rankings
        statistical_rankings = self._generate_statistical_rankings(basic_metrics, confidence_intervals)
        
        # Performance stability analysis
        stability_analysis = self._analyze_performance_stability(prompt_groups)
        
        # Sample size adequacy analysis
        sample_analysis = self._analyze_sample_adequacy(prompt_groups)
        
        # Generate insights and recommendations
        insights = self._generate_statistical_insights(
            basic_metrics, confidence_intervals, statistical_comparisons, stability_analysis
        )
        
        return {
            'analysis_type': analysis_type,
            'total_prompts': len(prompt_groups),
            'total_trades': len(trade_results),
            'basic_metrics': basic_metrics,
            'confidence_intervals': confidence_intervals,
            'statistical_comparisons': statistical_comparisons,
            'statistical_rankings': statistical_rankings,
            'stability_analysis': stability_analysis,
            'sample_analysis': sample_analysis,
            'insights': insights,
            'recommendations': self._generate_optimization_recommendations(insights)
        }
    
    def _group_trades_by_prompt(self, trade_results: List[Dict[str, Any]], 
                              analysis_type: str) -> Dict[str, List[Dict[str, Any]]]:
        """Group trade results by prompt identifier."""
        groups = defaultdict(list)
        
        prompt_key = 'prompt_hash' if analysis_type == 'hash' else 'prompt_version'
        
        for trade in trade_results:
            prompt_id = trade.get(prompt_key, 'unknown')
            groups[prompt_id].append(trade)
        
        return dict(groups)
    
    def _calculate_basic_metrics_by_prompt(self, prompt_groups: Dict[str, List[Dict]]) -> Dict[str, Dict[str, Any]]:
        """Calculate basic performance metrics for each prompt."""
        metrics = {}
        
        for prompt_id, trades in prompt_groups.items():
            wins = [t for t in trades if t['outcome'] == 'win']
            losses = [t for t in trades if t['outcome'] == 'loss']
            expired = [t for t in trades if t['outcome'] == 'expired']
            
            total_trades = len(trades)
            decisive_trades = len(wins) + len(losses)
            
            # Basic metrics
            win_rate = len(wins) / decisive_trades if decisive_trades > 0 else 0.0
            avg_rr = np.mean([t.get('achieved_rr', 0) for t in wins]) if wins else 0.0
            profit_factor = calculate_profit_factor(trades)
            
            # Duration analysis
            avg_duration = np.mean([t.get('duration_candles', 0) for t in trades])
            
            # Confidence analysis
            avg_confidence = np.mean([t.get('confidence', 0) for t in trades])
            
            # Expectancy calculation
            avg_win = np.mean([abs(t.get('take_profit', 0) - t.get('entry_price', 0)) * 
                             t.get('achieved_rr', 1) for t in wins]) if wins else 0.0
            avg_loss = np.mean([abs(t.get('entry_price', 0) - t.get('stop_loss', 0)) 
                              for t in losses]) if losses else 0.0
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
            
            metrics[prompt_id] = {
                'total_trades': total_trades,
                'decisive_trades': decisive_trades,
                'wins': len(wins),
                'losses': len(losses),
                'expired': len(expired),
                'win_rate': win_rate,
                'avg_rr': avg_rr,
                'profit_factor': profit_factor,
                'expectancy': expectancy,
                'avg_duration': avg_duration,
                'avg_confidence': avg_confidence
            }
        
        return metrics
    
    def _calculate_confidence_intervals_by_prompt(self, prompt_groups: Dict[str, List[Dict]]) -> Dict[str, Dict[str, Any]]:
        """Calculate confidence intervals for key metrics."""
        confidence_intervals = {}
        
        for prompt_id, trades in prompt_groups.items():
            wins = [t for t in trades if t['outcome'] == 'win']
            losses = [t for t in trades if t['outcome'] == 'loss']
            decisive_trades = len(wins) + len(losses)
            
            if decisive_trades == 0:
                confidence_intervals[prompt_id] = {
                    'win_rate': {'point_estimate': 0.0, 'ci_lower': 0.0, 'ci_upper': 0.0},
                    'sample_size': 0,
                    'confidence_level': 0.95
                }
                continue
            
            # Wilson confidence interval for win rate
            win_rate = len(wins) / decisive_trades
            ci_lower, ci_upper = self.statistical_framework.wilson_confidence_interval(
                len(wins), decisive_trades
            )
            
            # Bootstrap confidence interval for profit factor
            if len(trades) > 10:  # Minimum sample size for bootstrap
                pf_ci = self.statistical_framework.bootstrap_confidence_interval(
                    trades, calculate_profit_factor, n_bootstrap=500
                )
            else:
                pf_ci = (0.0, 0.0)
            
            confidence_intervals[prompt_id] = {
                'win_rate': {
                    'point_estimate': win_rate,
                    'ci_lower': ci_lower,
                    'ci_upper': ci_upper
                },
                'profit_factor': {
                    'point_estimate': calculate_profit_factor(trades),
                    'ci_lower': pf_ci[0],
                    'ci_upper': pf_ci[1]
                },
                'sample_size': decisive_trades,
                'confidence_level': 0.95
            }
        
        return confidence_intervals
    
    def _generate_statistical_rankings(self, basic_metrics: Dict[str, Dict], 
                                     confidence_intervals: Dict[str, Dict]) -> Dict[str, Any]:
        """Generate statistically-aware rankings of prompts."""
        
        # Create ranking data
        ranking_data = []
        for prompt_id, metrics in basic_metrics.items():
            ci_data = confidence_intervals.get(prompt_id, {})
            win_rate_ci = ci_data.get('win_rate', {})
            
            ranking_data.append({
                'prompt_id': prompt_id,
                'win_rate': metrics['win_rate'],
                'win_rate_lower': win_rate_ci.get('ci_lower', metrics['win_rate']),
                'win_rate_upper': win_rate_ci.get('ci_upper', metrics['win_rate']),
                'sample_size': metrics['decisive_trades'],
                'profit_factor': metrics['profit_factor'],
                'total_trades': metrics['total_trades']
            })
        
        # Sort by win rate (point estimate)
        ranking_data.sort(key=lambda x: x['win_rate'], reverse=True)
        
        # Add rankings
        for i, item in enumerate(ranking_data):
            item['rank'] = i + 1
            item['rank_reliable'] = item['sample_size'] >= 30
        
        # Identify statistically equivalent groups
        equivalent_groups = self._identify_equivalent_groups(ranking_data)
        
        return {
            'rankings': ranking_data,
            'equivalent_groups': equivalent_groups,
            'ranking_criteria': 'win_rate_with_confidence',
            'minimum_reliable_sample': 30
        }
    
    def _analyze_performance_stability(self, prompt_groups: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Analyze the stability of prompt performance over time."""
        stability_analysis = {}
        
        for prompt_id, trades in prompt_groups.items():
            if len(trades) < 10:  # Need minimum trades for stability analysis
                stability_analysis[prompt_id] = {
                    'stability_score': 0.0,
                    'trend': 'insufficient_data',
                    'volatility': 0.0
                }
                continue
            
            # Sort trades by timestamp
            sorted_trades = sorted(trades, key=lambda x: x.get('timestamp', ''))
            
            # Calculate rolling win rate
            window_size = max(10, len(trades) // 5)
            rolling_win_rates = []
            
            for i in range(window_size, len(sorted_trades)):
                window_trades = sorted_trades[i-window_size:i]
                wins = sum(1 for t in window_trades if t['outcome'] == 'win')
                losses = sum(1 for t in window_trades if t['outcome'] == 'loss')
                decisive = wins + losses
                
                if decisive > 0:
                    rolling_win_rates.append(wins / decisive)
            
            if len(rolling_win_rates) > 1:
                # Calculate stability metrics
                volatility = np.std(rolling_win_rates)
                trend = np.polyfit(range(len(rolling_win_rates)), rolling_win_rates, 1)[0]
                stability_score = max(0.0, 1.0 - float(volatility) * 2.0)  # Higher score = more stable
                
                # Categorize trend
                if abs(trend) < 0.01:
                    trend_category = 'stable'
                elif trend > 0:
                    trend_category = 'improving'
                else:
                    trend_category = 'declining'
            else:
                volatility = 0.0
                trend_category = 'insufficient_data'
                stability_score = 0.0
            
            stability_analysis[prompt_id] = {
                'stability_score': stability_score,
                'trend': trend_category,
                'volatility': volatility,
                'rolling_periods': len(rolling_win_rates)
            }
        
        return stability_analysis
    
    def _analyze_sample_adequacy(self, prompt_groups: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Analyze whether sample sizes are adequate for reliable conclusions."""
        
        sample_analysis = {}
        
        for prompt_id, trades in prompt_groups.items():
            wins = sum(1 for t in trades if t['outcome'] == 'win')
            losses = sum(1 for t in trades if t['outcome'] == 'loss')
            decisive_trades = wins + losses
            
            # Calculate required sample size for different effect sizes
            current_win_rate = wins / decisive_trades if decisive_trades > 0 else 0.5
            
            required_samples = {}
            effect_sizes = [0.05, 0.10, 0.15, 0.20]  # 5%, 10%, 15%, 20% difference
            
            for effect_size in effect_sizes:
                target_win_rate = min(0.95, current_win_rate + effect_size)
                required = self.statistical_framework.calculate_minimum_sample_size(
                    current_win_rate, target_win_rate
                )
                required_samples[f'{effect_size:.0%}_effect'] = required
            
            # Determine adequacy status
            if decisive_trades >= required_samples['5%_effect']:
                adequacy_status = 'excellent'
            elif decisive_trades >= required_samples['10%_effect']:
                adequacy_status = 'good'
            elif decisive_trades >= required_samples['15%_effect']:
                adequacy_status = 'moderate'
            elif decisive_trades >= 30:
                adequacy_status = 'minimal'
            else:
                adequacy_status = 'insufficient'
            
            sample_analysis[prompt_id] = {
                'current_sample_size': decisive_trades,
                'required_samples': required_samples,
                'adequacy_status': adequacy_status,
                'confidence_level': 'high' if decisive_trades >= 100 else 
                                  'medium' if decisive_trades >= 50 else 'low'
            }
        
        return sample_analysis
    
    def _identify_equivalent_groups(self, ranking_data: List[Dict]) -> List[List[str]]:
        """Identify groups of prompts with statistically equivalent performance."""
        equivalent_groups = []
        
        # Simple approach: group prompts with overlapping confidence intervals
        for i, prompt_a in enumerate(ranking_data):
            group = [prompt_a['prompt_id']]
            
            for j, prompt_b in enumerate(ranking_data[i+1:], i+1):
                # Check if confidence intervals overlap
                a_lower, a_upper = prompt_a['win_rate_lower'], prompt_a['win_rate_upper']
                b_lower, b_upper = prompt_b['win_rate_lower'], prompt_b['win_rate_upper']
                
                if not (a_upper < b_lower or b_upper < a_lower):  # Intervals overlap
                    group.append(prompt_b['prompt_id'])
            
            if len(group) > 1:
                equivalent_groups.append(group)
        
        return equivalent_groups

    def _identify_top_performers(self, basic_metrics: Dict[str, Dict], confidence_intervals: Dict[str, Dict],
                                top_n: int = 3) -> List[Dict[str, Any]]:
        """Identify top-performing prompts based on win rate and statistical reliability."""
        performers = []

        for prompt_id, metrics in basic_metrics.items():
            ci_data = confidence_intervals.get(prompt_id, {})
            sample_size = metrics.get('decisive_trades', 0)

            # Only consider prompts with adequate sample size
            if sample_size >= 30:
                performers.append({
                    'prompt_id': prompt_id,
                    'win_rate': metrics['win_rate'],
                    'sample_size': sample_size,
                    'ci_lower': ci_data.get('win_rate', {}).get('ci_lower', metrics['win_rate']),
                    'ci_upper': ci_data.get('win_rate', {}).get('ci_upper', metrics['win_rate'])
                })

        # Sort by win rate descending
        performers.sort(key=lambda x: x['win_rate'], reverse=True)

        return performers[:top_n]

    def _identify_underperformers(self, basic_metrics: Dict[str, Dict], confidence_intervals: Dict[str, Dict],
                                 bottom_n: int = 3) -> List[Dict[str, Any]]:
        """Identify underperforming prompts that could be discontinued."""
        performers = []

        for prompt_id, metrics in basic_metrics.items():
            ci_data = confidence_intervals.get(prompt_id, {})
            sample_size = metrics.get('decisive_trades', 0)

            # Only consider prompts with adequate sample size for fair comparison
            if sample_size >= 30:
                performers.append({
                    'prompt_id': prompt_id,
                    'win_rate': metrics['win_rate'],
                    'sample_size': sample_size,
                    'ci_lower': ci_data.get('win_rate', {}).get('ci_lower', metrics['win_rate']),
                    'ci_upper': ci_data.get('win_rate', {}).get('ci_upper', metrics['win_rate'])
                })

        # Sort by win rate ascending (worst performers first)
        performers.sort(key=lambda x: x['win_rate'])

        return performers[:bottom_n]

    def _generate_statistical_insights(self, basic_metrics: Dict, confidence_intervals: Dict,
                                     statistical_comparisons: Dict, stability_analysis: Dict) -> List[Dict[str, Any]]:
        """Generate actionable insights from statistical analysis."""
        insights = []
        
        # Find best performing prompt with statistical confidence
        if basic_metrics:
            best_prompt = max(basic_metrics.items(), key=lambda x: x[1]['win_rate'])
            best_prompt_id, best_metrics = best_prompt
            best_ci = confidence_intervals.get(best_prompt_id, {}).get('win_rate', {})
            
            insights.append({
                'type': 'best_performer',
                'title': f'Top Performing Prompt: {best_prompt_id}',
                'description': f'Achieves {best_metrics["win_rate"]:.1%} win rate with 95% confidence interval of [{best_ci.get("ci_lower", 0):.1%}, {best_ci.get("ci_upper", 0):.1%}]',
                'confidence': 'high' if best_metrics['decisive_trades'] >= 50 else 'medium',
                'actionable': f'Consider using {best_prompt_id} as your primary trading prompt'
            })
        
        # Identify prompts with insufficient sample sizes
        insufficient_samples = []
        for prompt_id, metrics in basic_metrics.items():
            if metrics['decisive_trades'] < 30:
                insufficient_samples.append(prompt_id)
        
        if insufficient_samples:
            insights.append({
                'type': 'sample_size_warning',
                'title': 'Insufficient Sample Sizes Detected',
                'description': f'{len(insufficient_samples)} prompts have fewer than 30 trades, making results unreliable',
                'confidence': 'high',
                'actionable': f'Collect more data for: {", ".join(insufficient_samples[:3])}{"..." if len(insufficient_samples) > 3 else ""}'
            })
        
        # Identify statistically significant differences
        if 'pairwise_comparisons' in statistical_comparisons:
            significant_pairs = []
            for comparison_key, result in statistical_comparisons['pairwise_comparisons'].items():
                if result.significant and result.effect_size > 0.1:  # Practical significance
                    significant_pairs.append((comparison_key, result))
            
            if significant_pairs:
                # Generate detailed recommendation with specific prompts and metrics
                top_performers = self._identify_top_performers(basic_metrics, confidence_intervals)
                underperformers = self._identify_underperformers(basic_metrics, confidence_intervals)

                # Calculate performance gaps
                if top_performers and underperformers:
                    top_avg = np.mean([p['win_rate'] for p in top_performers])
                    bottom_avg = np.mean([p['win_rate'] for p in underperformers])
                    performance_gap = top_avg - bottom_avg

                    # Build detailed recommendation
                    recommendation_parts = [
                        "🎯 Strategic Optimization Opportunity:",
                        f"• Top Performers: {', '.join([f'{p['prompt_id']} ({p['win_rate']:.1%})' for p in top_performers[:3]])}",
                        f"• Performance Gap: {performance_gap:.1%} between top and bottom performers",
                        f"• Statistical Confidence: {len(significant_pairs)} significant differences found (p<0.05)",
                        "",
                        "📋 Recommended Actions:",
                        f"1. Allocate 60% of trading capital to top {len(top_performers)} performers",
                        f"2. Discontinue {len(underperformers)} underperformers to save compute resources",
                        "3. A/B test top performer vs current production prompt",
                        "4. Monitor top performers for 30+ additional trades",
                        "",
                        "⚠️ Risk Considerations:",
                        "• Ensure sample sizes ≥100 trades before major allocation changes",
                        "• Monitor for performance degradation in new market conditions",
                        "• Consider transaction costs impact on small performance differences"
                    ]

                    detailed_recommendation = "\n".join(recommendation_parts)
                else:
                    detailed_recommendation = "Review top-performing prompts and consider discontinuing underperformers"

                insights.append({
                    'type': 'significant_differences',
                    'title': f'Found {len(significant_pairs)} Statistically Significant Differences',
                    'description': 'Some prompt pairs show meaningful performance differences',
                    'confidence': 'high',
                    'actionable': detailed_recommendation
                })
        
        # Identify declining performance trends
        declining_prompts = []
        for prompt_id, stability in stability_analysis.items():
            if stability['trend'] == 'declining' and stability['stability_score'] < 0.5:
                declining_prompts.append(prompt_id)
        
        if declining_prompts:
            insights.append({
                'type': 'performance_decline',
                'title': 'Performance Decline Detected',
                'description': f'{len(declining_prompts)} prompts show declining performance over time',
                'confidence': 'medium',
                'actionable': f'Investigate and potentially retire: {", ".join(declining_prompts[:2])}'
            })
        
        return insights
    
    def _generate_optimization_recommendations(self, insights: List[Dict]) -> List[Dict[str, Any]]:
        """Generate specific optimization recommendations based on insights."""
        recommendations = []
        
        for insight in insights:
            if insight['type'] == 'sample_size_warning':
                recommendations.append({
                    'category': 'data_collection',
                    'priority': 'high',
                    'recommendation': 'Increase data collection for prompts with small sample sizes',
                    'expected_impact': 'Improved reliability of performance metrics',
                    'implementation': 'Continue running backtests until 100+ decisive trades per prompt'
                })
            
            elif insight['type'] == 'performance_decline':
                recommendations.append({
                    'category': 'prompt_maintenance',
                    'priority': 'medium',
                    'recommendation': 'Review and update declining prompts',
                    'expected_impact': 'Prevent continued performance degradation',
                    'implementation': 'Analyze prompt content and market conditions for declining prompts'
                })
            
            elif insight['type'] == 'significant_differences':
                recommendations.append({
                    'category': 'strategy_optimization',
                    'priority': 'high',
                    'recommendation': 'Focus resources on top-performing prompts',
                    'expected_impact': 'Improved overall trading performance',
                    'implementation': 'Allocate more capital to statistically superior prompts'
                })
        
        return recommendations
