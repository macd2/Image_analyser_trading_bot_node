"""
SQLite-backed store for image backtest runs, images, analyses, trades, and summaries.
Keeps an append-only store (never removes rows) and deduplicates via UNIQUE constraints.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .utils import generate_prompt_hash


def generate_run_id() -> str:
    """Generate a unique run ID using UUID"""
    return f"bt_{uuid.uuid4().hex[:12]}"

# Use data/backtests.db relative to project root (V2/prototype)
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "backtests.db"


@dataclass
class RunInfo:
    run_id: str  # UUID string like "bt_abc123def456"
    run_signature: str


class BacktestStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(DB_PATH if db_path is None else db_path)
        self._ensure_db()

    def _ensure_db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            c = conn.cursor()
            # Runs table - using TEXT UUID for portable IDs
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    run_signature TEXT NOT NULL UNIQUE,
                    started_at TEXT,
                    finished_at TEXT,
                    duration_sec REAL,
                    charts_dir TEXT,
                    selection_strategy TEXT,
                    num_images INTEGER,
                    prompts_json TEXT,
                    symbols_json TEXT
                );
                """
            )
            # Images for a run
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS run_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    selection_order INTEGER NOT NULL,
                    UNIQUE(run_id, image_path),
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )
            # Analyses
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    prompt_name TEXT NOT NULL,
                    prompt_version TEXT,
                    prompt_hash TEXT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    recommendation TEXT,
                    confidence REAL,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    rr_ratio REAL,
                    status TEXT,
                    raw_response TEXT,
                    rationale TEXT,
                    error_message TEXT,
                    assistant_id TEXT,
                    assistant_model TEXT,
                    UNIQUE(run_id, prompt_name, image_path),
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )
            # Trades
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    prompt_name TEXT NOT NULL,
                    prompt_version TEXT,
                    prompt_hash TEXT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    confidence REAL,
                    rr_ratio REAL,
                    outcome TEXT,
                    duration_candles INTEGER,
                    achieved_rr REAL,
                    exit_price REAL,
                    exit_candle_index INTEGER,
                    entry_candle_index INTEGER,
                    mfe_price REAL,
                    mae_price REAL,
                    mfe_percent REAL,
                    mae_percent REAL,
                    mfe_r REAL,
                    mae_r REAL,
                    realized_pnl_price REAL,
                    realized_pnl_percent REAL,
                    image_path TEXT NOT NULL,
                    UNIQUE(run_id, prompt_name, image_path),
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )

            # Lightweight, idempotent migrations to add new columns when upgrading
            for ddl in [
                "ALTER TABLE analyses ADD COLUMN assistant_id TEXT",
                "ALTER TABLE analyses ADD COLUMN assistant_model TEXT",
                "ALTER TABLE trades ADD COLUMN entry_candle_index INTEGER",
                "ALTER TABLE trades ADD COLUMN mfe_price REAL",
                "ALTER TABLE trades ADD COLUMN mae_price REAL",
                "ALTER TABLE trades ADD COLUMN mfe_percent REAL",
                "ALTER TABLE trades ADD COLUMN mae_percent REAL",
                "ALTER TABLE trades ADD COLUMN mfe_r REAL",
                "ALTER TABLE trades ADD COLUMN mae_r REAL",
                "ALTER TABLE trades ADD COLUMN realized_pnl_price REAL",
                "ALTER TABLE trades ADD COLUMN realized_pnl_percent REAL"
            ]:
                try:
                    c.execute(ddl)
                except Exception:
                    # Ignore if column already exists
                    pass
            # Summaries
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    prompt_name TEXT NOT NULL,
                    total_trades INTEGER,
                    wins INTEGER,
                    losses INTEGER,
                    expired INTEGER,
                    win_rate REAL,
                    profit_factor REAL,
                    expectancy REAL,
                    avg_rr REAL,
                    avg_confidence REAL,
                    avg_duration REAL,
                    UNIQUE(run_id, prompt_name),
                    FOREIGN KEY(run_id) REFERENCES runs(id)
                );
                """
            )
            # Helpful indexes (wrapped in try-except for compatibility)
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_analyses_run_prompt ON analyses(run_id, prompt_name);",
                "CREATE INDEX IF NOT EXISTS idx_trades_run_prompt ON trades(run_id, prompt_name);",
                "CREATE INDEX IF NOT EXISTS idx_images_run ON run_images(run_id);"
            ]:
                try:
                    c.execute(idx_sql)
                except Exception as e:
                    # Ignore if index creation fails (e.g., column doesn't exist in old schema)
                    pass
            conn.commit()
            # === Prompt Optimizer Tables ===
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS opt_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT,
                    finished_at TEXT,
                    primary_metric TEXT,
                    config_json TEXT
                );
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS opt_iterations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    idx INTEGER NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    FOREIGN KEY(run_id) REFERENCES opt_runs(id)
                );
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS opt_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    prompt_text TEXT,
                    UNIQUE(run_id, signature),
                    FOREIGN KEY(run_id) REFERENCES opt_runs(id)
                );
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS opt_evals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    iteration INTEGER NOT NULL,
                    candidate_sig TEXT NOT NULL,
                    image_filename TEXT,
                    assistant_model TEXT,
                    metrics_json TEXT NOT NULL,
                    UNIQUE(run_id, iteration, candidate_sig, image_filename, assistant_model),
                    FOREIGN KEY(run_id) REFERENCES opt_runs(id)
                );
                """
            )
            # === Tournament Runs Table ===
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS tournament_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id TEXT NOT NULL UNIQUE,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT,
                    random_seed INTEGER,
                    config_json TEXT,
                    phase_details_json TEXT,
                    result_json TEXT,
                    winner TEXT,
                    win_rate REAL,
                    avg_pnl REAL,
                    total_api_calls INTEGER,
                    duration_sec REAL
                );
                """
            )
            conn.commit()

    # === Prompt Optimizer APIs ===
    def opt_create_run(self, *, started_at: str, primary_metric: str, config_json: str) -> int:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO opt_runs(started_at, primary_metric, config_json) VALUES (?, ?, ?)",
                (started_at, primary_metric, config_json),
            )
            conn.commit()
            return int(c.lastrowid)

    def opt_complete_run(self, run_id: int, *, finished_at: str) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("UPDATE opt_runs SET finished_at = ? WHERE id = ?", (finished_at, run_id))
            conn.commit()

    def opt_start_iteration(self, run_id: int, *, idx: int, started_at: str) -> int:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "INSERT INTO opt_iterations(run_id, idx, started_at) VALUES (?, ?, ?)",
                (run_id, idx, started_at),
            )
            conn.commit()
            return int(c.lastrowid)

    def opt_complete_iteration(self, iteration_id: int, *, finished_at: str) -> None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("UPDATE opt_iterations SET finished_at = ? WHERE id = ?", (finished_at, iteration_id))
            conn.commit()

    def opt_add_candidate(self, run_id: int, *, provider: str, model: str, signature: str, iteration: int, prompt_text: str) -> None:
        def _writer(conn: sqlite3.Connection) -> None:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR IGNORE INTO opt_candidates(run_id, provider, model, signature, iteration, prompt_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, provider, model, signature, iteration, prompt_text),
            )
        self._write_with_retry(_writer)

    def opt_add_eval(self, run_id: int, *, iteration: int, candidate_sig: str, metrics_json: str, image_filename: str | None, assistant_model: str | None) -> None:
        def _writer(conn: sqlite3.Connection) -> None:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR IGNORE INTO opt_evals(run_id, iteration, candidate_sig, image_filename, assistant_model, metrics_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, iteration, candidate_sig, image_filename, assistant_model, metrics_json),
            )
        self._write_with_retry(_writer)
    # === Prompt Optimizer Read APIs ===
    def opt_list_runs(self) -> list[dict]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, started_at, finished_at, primary_metric, config_json FROM opt_runs ORDER BY id DESC"
            )
            rows = c.fetchall()
            out: list[dict] = []
            for r in rows:
                out.append({
                    "id": r[0],
                    "started_at": r[1],
                    "finished_at": r[2],
                    "primary_metric": r[3],
                    "config_json": r[4],
                })
            return out

    def opt_get_run(self, run_id: int) -> dict | None:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("SELECT id, started_at, finished_at, primary_metric, config_json FROM opt_runs WHERE id = ?", (run_id,))
            r = c.fetchone()
            if not r:
                return None
            return {
                "id": r[0],
                "started_at": r[1],
                "finished_at": r[2],
                "primary_metric": r[3],
                "config_json": r[4],
            }

    def opt_get_candidates(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT provider, model, signature, iteration, prompt_text FROM opt_candidates WHERE run_id = ? ORDER BY iteration, id",
                (run_id,)
            )
            rows = c.fetchall()
            return [{"provider": r[0], "model": r[1], "signature": r[2], "iteration": r[3], "prompt_text": r[4]} for r in rows]

    def opt_get_evals_for_run(self, run_id: int) -> list[dict]:
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT iteration, candidate_sig, image_filename, assistant_model, metrics_json FROM opt_evals WHERE run_id = ? ORDER BY iteration, id",
                (run_id,)
            )
            rows = c.fetchall()
            return [{"iteration": r[0], "candidate_sig": r[1], "image_filename": r[2], "assistant_model": r[3], "metrics_json": r[4]} for r in rows]

    def opt_clear_all(self) -> None:
        """Danger: delete all optimizer runs (opt_* tables). Keeps other backtest data intact."""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM opt_evals")
            c.execute("DELETE FROM opt_candidates")
            c.execute("DELETE FROM opt_iterations")
            c.execute("DELETE FROM opt_runs")
            try:
                c.execute("VACUUM")
            except Exception:
                pass
            conn.commit()




    def _connect(self) -> sqlite3.Connection:
	        """SQLite connection with WAL and busy timeout to reduce lock errors."""
	        conn = sqlite3.connect(self.db_path, timeout=30)
	        try:
	            conn.execute("PRAGMA journal_mode=WAL;")
	        except Exception:
	            pass
	        try:
	            conn.execute("PRAGMA busy_timeout=5000;")  # milliseconds
	        except Exception:
	            pass
	        try:
	            conn.execute("PRAGMA synchronous=NORMAL;")
	        except Exception:
	            pass
	        return conn

    def _write_with_retry(self, writer, retries: int = 5, base_sleep: float = 0.05) -> None:
	        """Run a write operation with retry/backoff on 'database is locked'."""
	        import time as _time
	        delay = base_sleep
	        last_err: Optional[Exception] = None
	        for _ in range(retries):
	            try:
	                with self._connect() as conn:
	                    writer(conn)
	                    conn.commit()
	                return
	            except sqlite3.OperationalError as e:
	                last_err = e
	                if "locked" in str(e).lower():
	                    _time.sleep(delay)
	                    delay = min(delay * 2.0, 1.0)
	                    continue
	                raise
	            except Exception as e:  # non-lock error
	                last_err = e
	                raise
	        # Final attempt; if it still fails, propagate so caller can decide, but values remain in memory
	        if last_err is not None:
	            with self._connect() as conn:
	                writer(conn)
	                conn.commit()

    def create_or_get_run(self, *,
                          run_signature: str,
                          started_at: str,
                          charts_dir: str,
                          selection_strategy: str,
                          num_images: int,
                          prompts: List[str],
                          symbols: List[str]) -> RunInfo:
        with self._connect() as conn:
            c = conn.cursor()
            # Check if run already exists
            c.execute("SELECT id FROM runs WHERE run_signature = ?", (run_signature,))
            row = c.fetchone()
            if row:
                return RunInfo(run_id=row[0], run_signature=run_signature)

            # Generate new UUID for this run
            run_id = generate_run_id()
            c.execute(
                """
                INSERT INTO runs
                (id, run_signature, started_at, charts_dir, selection_strategy, num_images, prompts_json, symbols_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    run_signature,
                    started_at,
                    charts_dir,
                    selection_strategy,
                    num_images,
                    json.dumps(prompts),
                    json.dumps(symbols),
                ),
            )
            conn.commit()
            return RunInfo(run_id=run_id, run_signature=run_signature)

    def complete_run(self, run_id: str, *, finished_at: str, duration_sec: float):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                "UPDATE runs SET finished_at = ?, duration_sec = ? WHERE id = ?",
                (finished_at, duration_sec, run_id),
            )
            conn.commit()

    def add_run_images(self, run_id: str, images: Iterable[Dict[str, Any]]):
        with self._connect() as conn:
            c = conn.cursor()
            c.executemany(
                """
                INSERT OR IGNORE INTO run_images
                (run_id, symbol, timeframe, timestamp, image_path, selection_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        run_id,
                        img["symbol"],
                        img["timeframe"],
                        img["timestamp"],
                        img["image_path"],
                        img["selection_order"],
                    )
                    for img in images
                ],
            )
            conn.commit()

    def add_analysis(self, run_id: str, row: Dict[str, Any]):
        # Compute prompt hash if prompt text available; else from prompt_version/name
        prompt_text = row.get("prompt_text", "")
        p_hash = generate_prompt_hash(prompt_text) if prompt_text else None

        def _writer(conn: sqlite3.Connection) -> None:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR IGNORE INTO analyses
                (run_id, prompt_name, prompt_version, prompt_hash, symbol, timeframe, timestamp, image_path,
                 recommendation, confidence, entry_price, stop_loss, take_profit, rr_ratio, status, raw_response,
                 rationale, error_message, assistant_id, assistant_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row.get("prompt_name"),
                    row.get("prompt_version"),
                    p_hash,
                    row.get("symbol"),
                    row.get("timeframe"),
                    row.get("timestamp"),
                    row.get("image_path"),
                    row.get("recommendation"),
                    row.get("confidence"),
                    row.get("entry_price"),
                    row.get("stop_loss"),
                    row.get("take_profit"),
                    row.get("rr_ratio"),
                    row.get("status"),
                    row.get("raw_response"),
                    row.get("rationale"),
                    row.get("error_message"),
                    row.get("assistant_id"),
                    row.get("assistant_model"),
                ),
            )

        self._write_with_retry(_writer)

    def add_trade(self, run_id: str, row: Dict[str, Any]):
        # Derive realized PnL if missing
        direction = (row.get("recommendation") or row.get("direction") or "").lower()
        entry_price = row.get("entry_price")
        exit_price = row.get("exit_price")
        realized_pnl_price = row.get("realized_pnl_price")
        realized_pnl_percent = row.get("realized_pnl_percent")
        if realized_pnl_price is None and entry_price is not None and exit_price is not None:
            if direction == 'buy':
                realized_pnl_price = exit_price - entry_price
            elif direction == 'sell':
                realized_pnl_price = entry_price - exit_price
        if realized_pnl_percent is None and realized_pnl_price is not None and entry_price not in (None, 0):
            realized_pnl_percent = (realized_pnl_price / entry_price) * 100.0

        def _writer(conn: sqlite3.Connection) -> None:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR IGNORE INTO trades
                (run_id, prompt_name, prompt_version, prompt_hash, symbol, timeframe, timestamp, direction,
                 entry_price, stop_loss, take_profit, confidence, rr_ratio, outcome, duration_candles,
                 achieved_rr, exit_price, exit_candle_index, entry_candle_index,
                 mfe_price, mae_price, mfe_percent, mae_percent, mfe_r, mae_r,
                 realized_pnl_price, realized_pnl_percent,
                 image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    row.get("prompt_name"),
                    row.get("prompt_version"),
                    row.get("prompt_hash"),
                    row.get("symbol"),
                    row.get("timeframe"),
                    row.get("timestamp"),
                    direction or row.get("recommendation") or row.get("direction"),
                    entry_price,
                    row.get("stop_loss"),
                    row.get("take_profit"),
                    row.get("confidence"),
                    row.get("rr_ratio"),
                    row.get("outcome"),
                    row.get("duration_candles"),
                    row.get("achieved_rr"),
                    exit_price,
                    row.get("exit_candle_index"),
                    row.get("entry_candle_index"),
                    row.get("mfe_price"),
                    row.get("mae_price"),
                    row.get("mfe_percent"),
                    row.get("mae_percent"),
                    row.get("mfe_r"),
                    row.get("mae_r"),
                    realized_pnl_price,
                    realized_pnl_percent,
                    row.get("image_path"),
                ),
            )

        self._write_with_retry(_writer)

    def add_summary(self, run_id: str, prompt_name: str, metrics: Dict[str, Any]):
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT OR REPLACE INTO summaries
                (run_id, prompt_name, total_trades, wins, losses, expired, win_rate, profit_factor,
                 expectancy, avg_rr, avg_confidence, avg_duration)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    prompt_name,
                    metrics.get("total_trades", 0),
                    metrics.get("wins", 0),
                    metrics.get("losses", 0),
                    metrics.get("expired", 0),
                    metrics.get("win_rate", 0.0),
                    metrics.get("profit_factor", 0.0),
                    metrics.get("expectancy", 0.0),
                    metrics.get("avg_rr", 0.0),
                    metrics.get("avg_confidence", 0.0),
                    metrics.get("avg_duration", 0.0),
                ),
            )
            conn.commit()

    def has_cached_analysis(self, *, prompt_name: str, image_filename: str, assistant_model: Optional[str] = None, require_non_error: bool = True) -> bool:
        """Return True if an analysis exists for prompt_name + image filename.
        Behavior:
        - If assistant_model is provided, try exact model match first.
        - If that returns no row, fall back to any model for that prompt/image (non-error rows only if requested).
        - If assistant_model is None/empty, directly match any model.
        Uses a LIKE on image_path by filename only.
        """
        like_pattern = f"%{image_filename}"
        with self._connect() as conn:
            c = conn.cursor()
            # Try exact model match when provided
            if assistant_model:
                sql = (
                    "SELECT 1 FROM analyses WHERE prompt_name = ? "
                    "AND assistant_model = ? "
                    "AND image_path LIKE ? "
                )
                params = [prompt_name, assistant_model, like_pattern]
                if require_non_error:
                    sql += "AND (status IS NULL OR status != 'error') "
                sql += "LIMIT 1"
                c.execute(sql, params)
                if c.fetchone() is not None:
                    return True
            # Fallback: ignore model
            sql2 = (
                "SELECT 1 FROM analyses WHERE prompt_name = ? "
                "AND image_path LIKE ? "
            )
            params2 = [prompt_name, like_pattern]
            if require_non_error:
                sql2 += "AND (status IS NULL OR status != 'error') "
            sql2 += "LIMIT 1"
            c.execute(sql2, params2)
            return c.fetchone() is not None

    def get_cached_analysis(self, *, prompt_name: str, image_filename: str, assistant_model: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetch the most recent cached analysis for this prompt+image filename.
        If assistant_model is provided and non-empty, prefer an exact model match.
        Otherwise, match by prompt_name + image filename only (any model), non-error rows only.
        """
        like_pattern = f"%{image_filename}"
        with self._connect() as conn:
            c = conn.cursor()
            if assistant_model:
                params = (prompt_name, assistant_model, like_pattern)
                c.execute(
                    """
                    SELECT prompt_name, prompt_version, symbol, timeframe, timestamp, image_path,
                           recommendation, confidence, entry_price, stop_loss, take_profit,
                           rr_ratio, status, raw_response, rationale, error_message, assistant_id, assistant_model
                    FROM analyses
                    WHERE prompt_name = ?
                      AND assistant_model = ?
                      AND image_path LIKE ?
                      AND (status IS NULL OR status != 'error')
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    params,
                )
                row = c.fetchone()
                if row:
                    keys = [
                        'prompt_name','prompt_version','symbol','timeframe','timestamp','image_path',
                        'recommendation','confidence','entry_price','stop_loss','take_profit',
                        'rr_ratio','status','raw_response','rationale','error_message','assistant_id','assistant_model'
                    ]
                    return {k: v for k, v in zip(keys, row)}
            # Fallback: ignore model
            c.execute(
                """
                SELECT prompt_name, prompt_version, symbol, timeframe, timestamp, image_path,
                       recommendation, confidence, entry_price, stop_loss, take_profit,
                       rr_ratio, status, raw_response, rationale, error_message, assistant_id, assistant_model
                FROM analyses
                WHERE prompt_name = ?
                  AND image_path LIKE ?
                  AND (status IS NULL OR status != 'error')
                ORDER BY id DESC
                LIMIT 1
                """,
                (prompt_name, like_pattern),
            )
            row = c.fetchone()
            if not row:
                return None
            keys = [
                'prompt_name','prompt_version','symbol','timeframe','timestamp','image_path',
                'recommendation','confidence','entry_price','stop_loss','take_profit',
                'rr_ratio','status','raw_response','rationale','error_message','assistant_id','assistant_model'
            ]
            return {k: v for k, v in zip(keys, row)}

    # Utility to compute a stable signature for a run
    @staticmethod
    def compute_signature(*, image_paths: List[str], prompts: List[str], symbols: List[str], num_images: int, charts_dir: str) -> str:
        import hashlib
        key = "|".join([
            ",".join(sorted(image_paths)),
            ",".join(sorted(prompts)),
            ",".join(sorted(symbols)),
            str(num_images),
            charts_dir,
        ])
        return hashlib.sha1(key.encode()).hexdigest()[:12]

    # Migration utility: rename prompt names in-place with collision avoidance
    def rename_prompt_names(self, mapping: Dict[str, str]) -> Dict[str, int]:
        """Rename prompt_name values according to mapping for both analyses and trades.
        Avoid UNIQUE(run_id, prompt_name, image_path) conflicts by skipping rows where
        the target already exists. Returns counts of updated rows per table.
        """
        analyses_updated_total = 0
        trades_updated_total = 0
        with self._connect() as conn:
            c = conn.cursor()
            for old, new in mapping.items():
                # Analyses
                c.execute(
                    """
                    UPDATE analyses
                    SET prompt_name = ?
                    WHERE prompt_name = ?
                      AND NOT EXISTS (
                        SELECT 1 FROM analyses a2
                        WHERE a2.run_id = analyses.run_id
                          AND a2.image_path = analyses.image_path
                          AND a2.prompt_name = ?
                      )
                    """,
                    (new, old, new),
                )
                analyses_updated_total += c.rowcount if c.rowcount is not None else 0

                # Trades
                c.execute(
                    """
                    UPDATE trades
                    SET prompt_name = ?
                    WHERE prompt_name = ?
                      AND NOT EXISTS (
                        SELECT 1 FROM trades t2
                        WHERE t2.run_id = trades.run_id
                          AND t2.image_path = trades.image_path
                          AND t2.prompt_name = ?
                      )
                    """,
                    (new, old, new),
                )
                trades_updated_total += c.rowcount if c.rowcount is not None else 0

            conn.commit()
        return {"analyses_updated": analyses_updated_total, "trades_updated": trades_updated_total}

    # === Tournament APIs ===
    def tournament_create(self, tournament_id: str, started_at: str, config: dict, random_seed: int) -> int:
        """Create a new tournament run."""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """INSERT INTO tournament_runs(tournament_id, started_at, status, random_seed, config_json)
                   VALUES (?, ?, 'running', ?, ?)""",
                (tournament_id, started_at, random_seed, json.dumps(config))
            )
            conn.commit()
            return c.lastrowid or 0

    def tournament_complete(self, tournament_id: str, finished_at: str, status: str,
                           phase_details: dict, result: dict) -> None:
        """Mark tournament as complete with results."""
        winner = result.get('winner', '')
        win_rate = result.get('win_rate', 0)
        avg_pnl = result.get('avg_pnl', 0)
        total_api_calls = result.get('total_api_calls', 0)
        duration_sec = result.get('duration_sec', 0)
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """UPDATE tournament_runs SET
                   finished_at = ?, status = ?, phase_details_json = ?, result_json = ?,
                   winner = ?, win_rate = ?, avg_pnl = ?, total_api_calls = ?, duration_sec = ?
                   WHERE tournament_id = ?""",
                (finished_at, status, json.dumps(phase_details), json.dumps(result),
                 winner, win_rate, avg_pnl, total_api_calls, duration_sec, tournament_id)
            )
            conn.commit()

    def tournament_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent tournament runs."""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT id, tournament_id, started_at, finished_at, status, random_seed,
                          config_json, winner, win_rate, avg_pnl, total_api_calls, duration_sec
                   FROM tournament_runs ORDER BY id DESC LIMIT ?""",
                (limit,)
            )
            rows = c.fetchall()
            return [
                {
                    'id': r[0], 'tournament_id': r[1], 'started_at': r[2], 'finished_at': r[3],
                    'status': r[4], 'random_seed': r[5],
                    'config': json.loads(r[6]) if r[6] else {},
                    'winner': r[7], 'win_rate': r[8], 'avg_pnl': r[9],
                    'total_api_calls': r[10], 'duration_sec': r[11]
                }
                for r in rows
            ]

    def tournament_get(self, tournament_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific tournament run with full details."""
        with self._connect() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT id, tournament_id, started_at, finished_at, status, random_seed,
                          config_json, phase_details_json, result_json,
                          winner, win_rate, avg_pnl, total_api_calls, duration_sec
                   FROM tournament_runs WHERE tournament_id = ?""",
                (tournament_id,)
            )
            r = c.fetchone()
            if not r:
                return None
            return {
                'id': r[0], 'tournament_id': r[1], 'started_at': r[2], 'finished_at': r[3],
                'status': r[4], 'random_seed': r[5],
                'config': json.loads(r[6]) if r[6] else {},
                'phase_details': json.loads(r[7]) if r[7] else {},
                'result': json.loads(r[8]) if r[8] else {},
                'winner': r[9], 'win_rate': r[10], 'avg_pnl': r[11],
                'total_api_calls': r[12], 'duration_sec': r[13]
            }
