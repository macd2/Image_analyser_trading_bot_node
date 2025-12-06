"""
A/B testing framework for prompt comparison with statistical rigor.
Provides experiment design, real-time monitoring, and statistical analysis.
"""

import uuid
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
import pandas as pd
import logging

from statistical_testing import StatisticalTestingFramework

logger = logging.getLogger(__name__)

class TestStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"

@dataclass
class ABTestConfig:
    """Configuration for an A/B test experiment."""
    test_id: str
    test_name: str
    prompt_a_id: str  # Control
    prompt_b_id: str  # Variant
    symbols: List[str]
    timeframes: List[str]
    target_sample_size: int
    max_duration_days: int
    significance_level: float = 0.05
    minimum_effect_size: float = 0.05
    power: float = 0.80
    early_stopping_enabled: bool = True
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

@dataclass 
class ABTestResult:
    """Real-time results of an A/B test."""
    test_id: str
    status: TestStatus
    current_sample_size_a: int
    current_sample_size_b: int
    current_wins_a: int
    current_wins_b: int
    current_p_value: float
    current_effect_size: float
    confidence_interval: Tuple[float, float]
    statistical_power: float
    days_running: int
    last_updated: datetime
    
class ABTestManager:
    """Manages A/B testing experiments for prompt comparison."""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            from pathlib import Path
            db_path = str(Path(__file__).parent.parent / "ab_tests.db")
        
        self.db_path = db_path
        self.statistical_framework = StatisticalTestingFramework()
        self._initialize_database()
    
    def _initialize_database(self):
        """Create necessary database tables for A/B testing."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ab_tests (
                    test_id TEXT PRIMARY KEY,
                    config TEXT,
                    status TEXT,
                    created_at TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS ab_test_results (
                    result_id TEXT PRIMARY KEY,
                    test_id TEXT,
                    trade_data TEXT,
                    group_assignment TEXT,
                    recorded_at TIMESTAMP,
                    FOREIGN KEY (test_id) REFERENCES ab_tests (test_id)
                )
            ''')
            
            conn.commit()
    
    def create_experiment(self, config: ABTestConfig) -> str:
        """Create a new A/B test experiment."""
        
        # Validate configuration
        validation_result = self._validate_experiment_config(config)
        if not validation_result['valid']:
            raise ValueError(f"Invalid experiment configuration: {validation_result['errors']}")
        
        # Calculate actual required sample size
        config.target_sample_size = self.statistical_framework.calculate_minimum_sample_size(
            p1=0.65,  # Assumed baseline win rate
            p2=0.65 + config.minimum_effect_size,
            power=config.power,
            alpha=config.significance_level
        )
        
        # Store experiment in database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO ab_tests (test_id, config, status, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                config.test_id,
                json.dumps(asdict(config), default=str),
                TestStatus.DRAFT.value,
                config.created_at
            ))
            conn.commit()
        
        logger.info(f"Created A/B test experiment: {config.test_id}")
        return config.test_id
    
    def start_experiment(self, test_id: str) -> bool:
        """Start running an A/B test experiment."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE ab_tests 
                SET status = ?, started_at = ?
                WHERE test_id = ?
            ''', (TestStatus.RUNNING.value, datetime.utcnow(), test_id))
            conn.commit()
        
        logger.info(f"Started A/B test: {test_id}")
        return True
    
    def stop_experiment(self, test_id: str, reason: str = "Manual stop") -> bool:
        """Stop a running experiment."""
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE ab_tests 
                SET status = ?, completed_at = ?
                WHERE test_id = ?
            ''', (TestStatus.STOPPED.value, datetime.utcnow(), test_id))
            conn.commit()
        
        logger.info(f"Stopped A/B test {test_id}: {reason}")
        return True
    
    def record_trade_result(self, test_id: str, trade_data: Dict[str, Any]) -> None:
        """Record a trade result for an active A/B test."""
        
        # Get test configuration
        config = self._get_test_config(test_id)
        if not config or config['status'] != TestStatus.RUNNING.value:
            return
        
        # Determine group assignment (50/50 random split)
        group_assignment = 'A' if np.random.random() < 0.5 else 'B'
        
        # Store result
        result_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO ab_test_results (result_id, test_id, trade_data, group_assignment, recorded_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                result_id,
                test_id,
                json.dumps(trade_data),
                group_assignment,
                datetime.utcnow()
            ))
            conn.commit()
        
        # Check for early stopping or completion
        self._check_test_completion(test_id)
    
    def get_test_results(self, test_id: str) -> ABTestResult:
        """Get current results for an A/B test."""
        
        # Get test configuration
        config_row = self._get_test_config(test_id)
        if not config_row:
            raise ValueError(f"Test {test_id} not found")
        
        config = json.loads(config_row['config'])
        
        # Get all results for this test
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT trade_data, group_assignment, recorded_at
                FROM ab_test_results
                WHERE test_id = ?
                ORDER BY recorded_at
            ''', (test_id,))
            
            results = cursor.fetchall()
        
        # Separate results by group
        group_a_results = []
        group_b_results = []
        
        for row in results:
            trade_data = json.loads(row[0])
            group = row[1]
            
            if group == 'A':
                group_a_results.append(trade_data)
            else:
                group_b_results.append(trade_data)
        
        # Calculate current statistics
        current_stats = self._calculate_current_statistics(group_a_results, group_b_results)
        
        # Calculate days running
        start_date = datetime.fromisoformat(config_row['started_at']) if config_row['started_at'] else datetime.fromisoformat(config_row['created_at'])
        days_running = (datetime.utcnow() - start_date).days
        
        return ABTestResult(
            test_id=test_id,
            status=TestStatus(config_row['status']),
            current_sample_size_a=len(group_a_results),
            current_sample_size_b=len(group_b_results),
            current_wins_a=current_stats['wins_a'],
            current_wins_b=current_stats['wins_b'],
            current_p_value=current_stats['p_value'],
            current_effect_size=current_stats['effect_size'],
            confidence_interval=current_stats['confidence_interval'],
            statistical_power=current_stats['power'],
            days_running=days_running,
            last_updated=datetime.utcnow()
        )
    
    def get_active_experiments(self) -> List[Dict[str, Any]]:
        """Get all active experiments."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM ab_tests 
                WHERE status IN (?, ?)
                ORDER BY created_at DESC
            ''', (TestStatus.RUNNING.value, TestStatus.PAUSED.value))
            
            experiments = []
            for row in cursor.fetchall():
                config = json.loads(row['config'])
                experiments.append({
                    'test_id': row['test_id'],
                    'test_name': config['test_name'],
                    'status': row['status'],
                    'created_at': row['created_at'],
                    'started_at': row['started_at'],
                    'config': config
                })
            
            return experiments
    
    def _validate_experiment_config(self, config: ABTestConfig) -> Dict[str, Any]:
        """Validate experiment configuration."""
        errors = []
        
        if not config.test_name or len(config.test_name.strip()) == 0:
            errors.append("Test name is required")
        
        if not config.prompt_a_id or not config.prompt_b_id:
            errors.append("Both prompt A and prompt B must be specified")
        
        if config.prompt_a_id == config.prompt_b_id:
            errors.append("Prompt A and Prompt B must be different")
        
        if not config.symbols or len(config.symbols) == 0:
            errors.append("At least one symbol must be specified")
        
        if not config.timeframes or len(config.timeframes) == 0:
            errors.append("At least one timeframe must be specified")
        
        if config.significance_level <= 0 or config.significance_level >= 1:
            errors.append("Significance level must be between 0 and 1")
        
        if config.power <= 0 or config.power >= 1:
            errors.append("Statistical power must be between 0 and 1")
        
        if config.max_duration_days <= 0:
            errors.append("Maximum duration must be positive")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def _get_test_config(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get test configuration from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM ab_tests WHERE test_id = ?
            ''', (test_id,))
            
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def _calculate_current_statistics(self, group_a_results: List[Dict], 
                                   group_b_results: List[Dict]) -> Dict[str, Any]:
        """Calculate current test statistics."""
        
        if not group_a_results or not group_b_results:
            return {
                'wins_a': 0, 'wins_b': 0, 'p_value': 1.0, 'effect_size': 0.0,
                'confidence_interval': (0.0, 0.0), 'power': 0.0
            }
        
        # Count wins
        wins_a = sum(1 for trade in group_a_results if trade.get('outcome') == 'win')
        wins_b = sum(1 for trade in group_b_results if trade.get('outcome') == 'win')
        
        # Perform statistical test
        test_result = self.statistical_framework.two_proportion_test(group_a_results, group_b_results)
        
        # Calculate statistical power (simplified)
        p1 = wins_a / len(group_a_results) if len(group_a_results) > 0 else 0
        p2 = wins_b / len(group_b_results) if len(group_b_results) > 0 else 0
        
        try:
            effect_size = 2 * (np.arcsin(np.sqrt(p1)) - np.arcsin(np.sqrt(p2)))
            # Simplified power calculation
            n = min(len(group_a_results), len(group_b_results))
            power = min(0.99, max(0.05, abs(effect_size) * np.sqrt(n) / 4))
        except:
            power = 0.0
        
        return {
            'wins_a': wins_a,
            'wins_b': wins_b,
            'p_value': test_result.p_value,
            'effect_size': test_result.effect_size,
            'confidence_interval': test_result.confidence_interval,
            'power': power
        }
    
    def _check_test_completion(self, test_id: str) -> None:
        """Check if test should be stopped due to completion criteria."""
        
        config_row = self._get_test_config(test_id)
        if not config_row:
            return
        
        config = json.loads(config_row['config'])
        current_results = self.get_test_results(test_id)
        
        # Check for sample size completion
        total_sample_size = current_results.current_sample_size_a + current_results.current_sample_size_b
        if total_sample_size >= config['target_sample_size']:
            self._complete_test(test_id, "Target sample size reached")
            return
        
        # Check for time limit
        if current_results.days_running >= config['max_duration_days']:
            self._complete_test(test_id, "Maximum duration reached")
            return
        
        # Check for early stopping (if enabled)
        if (config.get('early_stopping_enabled', True) and 
            total_sample_size >= config['target_sample_size'] * 0.5 and  # At least 50% of target
            current_results.current_p_value < 0.01):  # Very significant result
            self._complete_test(test_id, "Early stopping - significant result achieved")
            return
    
    def _complete_test(self, test_id: str, reason: str) -> None:
        """Mark test as completed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE ab_tests 
                SET status = ?, completed_at = ?
                WHERE test_id = ?
            ''', (TestStatus.COMPLETED.value, datetime.utcnow(), test_id))
            conn.commit()
        
        logger.info(f"Completed A/B test {test_id}: {reason}")

def generate_test_id() -> str:
    """Generate a unique test ID."""
    return f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

def create_sample_experiment() -> ABTestConfig:
    """Create a sample A/B test configuration for demonstration."""
    return ABTestConfig(
        test_id=generate_test_id(),
        test_name="Sample Prompt Comparison",
        prompt_a_id="prompt_v1_baseline",
        prompt_b_id="prompt_v2_enhanced",
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=["1h", "4h"],
        target_sample_size=200,  # Will be recalculated
        max_duration_days=30,
        significance_level=0.05,
        minimum_effect_size=0.05,
        power=0.80,
        early_stopping_enabled=True
    )