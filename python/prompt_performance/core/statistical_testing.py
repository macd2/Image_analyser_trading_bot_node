"""
Comprehensive statistical testing framework for prompt performance analysis.
Includes hypothesis testing, multiple comparison corrections, and effect size calculations.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional, Callable
import logging
from dataclasses import dataclass
import random
import math

# Optional imports with fallbacks
try:
    import scipy.stats as scipy_stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    scipy_stats = None

# Create a stats module with fallback implementations
class StatsModule:
    @staticmethod
    def norm_cdf(x):
        """Standard normal CDF approximation."""
        return 0.5 + 0.5 * math.erf(x / math.sqrt(2))
    
    @staticmethod
    def norm_ppf(p):
        """Standard normal PPF approximation."""
        return math.sqrt(2) * _inverse_erf(2 * p - 1)

stats_module = StatsModule()

def _inverse_erf(x):
    """Simple approximation of inverse error function."""
    # Using Abramowitz and Stegun approximation
    a = 0.147
    sign = 1 if x >= 0 else -1
    x = abs(x)
    
    ln_term = math.log(1 - x**2)
    sqrt_term = math.sqrt(
        (2 / (math.pi * a)) + ln_term/2
    )
    
    result = sign * math.sqrt(
        sqrt_term - ln_term/2
    )
    
    return result

logger = logging.getLogger(__name__)

@dataclass
class StatisticalTestResult:
    """Results from a statistical test."""
    test_statistic: float
    p_value: float
    effect_size: float
    confidence_interval: Tuple[float, float]
    sample_sizes: Tuple[int, int]
    win_rates: Tuple[float, float]
    interpretation: str
    significant: bool
    corrected_p_value: Optional[float] = None
    significant_corrected: Optional[bool] = None

class StatisticalTestingFramework:
    """
    Comprehensive statistical testing framework for prompt performance analysis.
    Includes hypothesis testing, multiple comparison corrections, and effect size calculations.
    """
    
    def __init__(self, alpha: float = 0.05, correction_method: str = 'fdr_bh'):
        self.alpha = alpha
        self.correction_method = correction_method
        self.test_results = {}
    
    def two_proportion_test(self, group_a: List[Dict], group_b: List[Dict]) -> StatisticalTestResult:
        """
        Perform two-proportion z-test for comparing win rates between prompts.
        
        Args:
            group_a: List of trade results for prompt A
            group_b: List of trade results for prompt B
            
        Returns:
            StatisticalTestResult object containing test statistics and interpretation
        """
        try:
            # Calculate successes and sample sizes
            wins_a = sum(1 for trade in group_a if trade['outcome'] == 'win')
            losses_a = sum(1 for trade in group_a if trade['outcome'] == 'loss')
            total_a = wins_a + losses_a
            
            wins_b = sum(1 for trade in group_b if trade['outcome'] == 'win')
            losses_b = sum(1 for trade in group_b if trade['outcome'] == 'loss')
            total_b = wins_b + losses_b
            
            if total_a == 0 or total_b == 0:
                return StatisticalTestResult(
                    test_statistic=np.nan,
                    p_value=np.nan,
                    effect_size=np.nan,
                    confidence_interval=(np.nan, np.nan),
                    sample_sizes=(total_a, total_b),
                    win_rates=(0.0, 0.0),
                    interpretation='Insufficient data for testing',
                    significant=False
                )
            
            # Calculate proportions
            p1 = wins_a / total_a
            p2 = wins_b / total_b
            
            # Perform two-proportion z-test using normal approximation
            p_pool = (wins_a + wins_b) / (total_a + total_b)
            se = np.sqrt(p_pool * (1 - p_pool) * (1/total_a + 1/total_b))
            
            if se == 0:
                z_stat = 0
                p_value = 1.0
            else:
                z_stat = (p1 - p2) / se
                if SCIPY_AVAILABLE and scipy_stats:
                    p_value = 2 * (1 - scipy_stats.norm.cdf(abs(z_stat)))
                else:
                    p_value = 2 * (1 - stats_module.norm_cdf(abs(z_stat)))
            
            # Calculate effect size (Cohen's h)
            effect_size = 2 * (np.arcsin(np.sqrt(p1)) - np.arcsin(np.sqrt(p2)))
            
            # Calculate confidence interval for difference in proportions
            diff = p1 - p2
            se_diff = np.sqrt(p1 * (1 - p1) / total_a + p2 * (1 - p2) / total_b)
            ci_lower = diff - 1.96 * se_diff
            ci_upper = diff + 1.96 * se_diff
            
            # Interpret results
            interpretation = self._interpret_two_proportion_test(
                p_value, effect_size, p1, p2, total_a, total_b
            )
            
            return StatisticalTestResult(
                test_statistic=z_stat,
                p_value=p_value,
                effect_size=effect_size,
                confidence_interval=(ci_lower, ci_upper),
                sample_sizes=(total_a, total_b),
                win_rates=(p1, p2),
                interpretation=interpretation,
                significant=p_value < self.alpha
            )
            
        except Exception as e:
            logger.error(f"Error in two-proportion test: {e}")
            return StatisticalTestResult(
                test_statistic=np.nan,
                p_value=np.nan,
                effect_size=np.nan,
                confidence_interval=(np.nan, np.nan),
                sample_sizes=(0, 0),
                win_rates=(0.0, 0.0),
                interpretation=f'Error in statistical test: {str(e)}',
                significant=False
            )
    
    def perform_multiple_comparisons(self, prompt_groups: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """
        Perform pairwise comparisons between all prompts with multiple testing correction.
        
        Args:
            prompt_groups: Dictionary mapping prompt IDs to list of trade results
            
        Returns:
            Dictionary containing all pairwise comparisons with corrected p-values
        """
        prompt_ids = list(prompt_groups.keys())
        comparisons = {}
        p_values = []
        comparison_keys = []
        
        # Perform all pairwise tests
        for i, prompt_a in enumerate(prompt_ids):
            for prompt_b in prompt_ids[i+1:]:
                comparison_key = f"{prompt_a}_vs_{prompt_b}"
                
                test_result = self.two_proportion_test(
                    prompt_groups[prompt_a],
                    prompt_groups[prompt_b]
                )
                
                comparisons[comparison_key] = test_result
                if not np.isnan(test_result.p_value):
                    p_values.append(test_result.p_value)
                    comparison_keys.append(comparison_key)
        
        # Apply multiple testing correction
        if p_values and len(p_values) > 1:
            try:
                from statsmodels.stats.multitest import multipletests
                rejected, corrected_p_values, _, _ = multipletests(
                    p_values,
                    alpha=self.alpha,
                    method=self.correction_method
                )
                
                # Update comparisons with corrected p-values
                for i, comparison_key in enumerate(comparison_keys):
                    comparisons[comparison_key].corrected_p_value = corrected_p_values[i]
                    comparisons[comparison_key].significant_corrected = rejected[i]
                    
            except ImportError:
                logger.warning("statsmodels not available, using Bonferroni correction")
                # Use simple Bonferroni correction as fallback
                bonferroni_alpha = self.alpha / len(p_values)
                for comparison_key in comparison_keys:
                    original_p = comparisons[comparison_key].p_value
                    comparisons[comparison_key].corrected_p_value = min(1.0, original_p * len(p_values))
                    comparisons[comparison_key].significant_corrected = original_p < bonferroni_alpha
        
        return {
            'pairwise_comparisons': comparisons,
            'correction_method': self.correction_method,
            'family_wise_error_rate': self.alpha,
            'number_of_comparisons': len(comparisons)
        }
    
    def wilson_confidence_interval(self, successes: int, total: int, 
                                 confidence_level: float = 0.95) -> Tuple[float, float]:
        """
        Calculate Wilson score confidence interval for proportion.
        More accurate than normal approximation for small sample sizes.
        """
        if total == 0:
            return (0, 0)
        
        if SCIPY_AVAILABLE and scipy_stats:
            z = scipy_stats.norm.ppf(1 - (1 - confidence_level) / 2)
        else:
            z = stats_module.norm_ppf(1 - (1 - confidence_level) / 2)
        p = successes / total
        
        denominator = 1 + z**2 / total
        center = (p + z**2 / (2 * total)) / denominator
        margin = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominator
        
        return (max(0, center - margin), min(1, center + margin))
    
    def calculate_minimum_sample_size(self, p1: float, p2: float, 
                                    power: float = 0.8, alpha: float = 0.05) -> int:
        """
        Calculate minimum sample size needed to detect difference between two proportions.
        
        Args:
            p1: Expected proportion for group 1
            p2: Expected proportion for group 2  
            power: Desired statistical power (1 - β)
            alpha: Significance level
            
        Returns:
            Minimum sample size per group
        """
        try:
            # Calculate effect size
            effect_size = 2 * (np.arcsin(np.sqrt(p1)) - np.arcsin(np.sqrt(p2)))
            
            if abs(effect_size) < 0.001:  # Very small effect size
                return 10000  # Return large number
            
            # Use simplified formula for sample size calculation
            if SCIPY_AVAILABLE and scipy_stats:
                z_alpha = scipy_stats.norm.ppf(1 - alpha/2)
                z_beta = scipy_stats.norm.ppf(power)
            else:
                z_alpha = stats_module.norm_ppf(1 - alpha/2)
                z_beta = stats_module.norm_ppf(power)
            
            p_avg = (p1 + p2) / 2
            
            numerator = (z_alpha * np.sqrt(2 * p_avg * (1 - p_avg)) + 
                        z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2)))**2
            denominator = (p1 - p2)**2
            
            n = numerator / denominator
            
            return max(30, int(np.ceil(n)))  # Minimum of 30 samples
            
        except Exception as e:
            logger.error(f"Error calculating sample size: {e}")
            return 100  # Default reasonable sample size
    
    def bootstrap_confidence_interval(self, data: List[Dict],
                                    statistic_func: Callable[[List[Dict]], float],
                                    n_bootstrap: int = 1000,
                                    confidence_level: float = 0.95) -> Tuple[float, float]:
        """
        Calculate bootstrap confidence interval for any statistic.
        
        Args:
            data: List of trade results
            statistic_func: Function that calculates the statistic from data
            n_bootstrap: Number of bootstrap samples
            confidence_level: Confidence level for interval
            
        Returns:
            Tuple of (lower_bound, upper_bound)
        """
        if len(data) == 0:
            return (0.0, 0.0)
        
        bootstrap_stats = []
        
        for _ in range(n_bootstrap):
            # Bootstrap sample using random.choices instead of np.random.choice
            try:
                bootstrap_sample = random.choices(data, k=len(data))
                bootstrap_stat = statistic_func(bootstrap_sample)
                if not np.isnan(bootstrap_stat):
                    bootstrap_stats.append(bootstrap_stat)
            except Exception as e:
                continue
        
        if not bootstrap_stats:
            return (0.0, 0.0)
        
        # Calculate confidence interval
        alpha = 1 - confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100
        
        ci_lower = float(np.percentile(bootstrap_stats, lower_percentile))
        ci_upper = float(np.percentile(bootstrap_stats, upper_percentile))
        
        return (ci_lower, ci_upper)
    
    def _interpret_two_proportion_test(self, p_value: float, effect_size: float,
                                     p1: float, p2: float, n1: int, n2: int) -> str:
        """Generate human-readable interpretation of test results."""
        
        interpretation = []
        
        # Statistical significance
        if p_value < 0.001:
            interpretation.append("Highly significant difference (p < 0.001)")
        elif p_value < 0.01:
            interpretation.append("Very significant difference (p < 0.01)")
        elif p_value < 0.05:
            interpretation.append("Significant difference (p < 0.05)")
        else:
            interpretation.append("No significant difference detected")
        
        # Effect size magnitude
        abs_effect = abs(effect_size)
        if abs_effect < 0.2:
            interpretation.append("Small effect size")
        elif abs_effect < 0.5:
            interpretation.append("Medium effect size")
        else:
            interpretation.append("Large effect size")
        
        # Practical interpretation
        diff_percentage = abs(p1 - p2) * 100
        better_prompt = "A" if p1 > p2 else "B"
        interpretation.append(f"Prompt {better_prompt} has {diff_percentage:.1f}% higher win rate")
        
        # Sample size adequacy
        min_sample = min(n1, n2)
        if min_sample < 30:
            interpretation.append("⚠️ Small sample size - results may be unreliable")
        elif min_sample < 100:
            interpretation.append("Moderate sample size - results are reasonably reliable")
        else:
            interpretation.append("Large sample size - results are highly reliable")
        
        return " | ".join(interpretation)


def calculate_profit_factor(trades: List[Dict]) -> float:
    """Calculate profit factor from trade results."""
    wins = [t for t in trades if t.get('outcome') == 'win']
    losses = [t for t in trades if t.get('outcome') == 'loss']
    
    if not losses:
        return float('inf') if wins else 0.0
    
    total_profit = sum(abs(t.get('take_profit', 0) - t.get('entry_price', 0)) * 
                      t.get('achieved_rr', 1) for t in wins)
    total_loss = sum(abs(t.get('entry_price', 0) - t.get('stop_loss', 0)) for t in losses)
    
    return total_profit / total_loss if total_loss > 0 else 0.0