/**
 * Tournament Database Operations
 * CRUD operations for the tournament system
 */

import { getDb } from './migrate';

export interface TournamentConfig {
  name: string;
  model: string;
  eliminationPct: number;
  imagesPhase1: number;
  imagesPhase2: number;
  imagesPhase3: number;
  imageOffset: number;
  selectionStrategy: 'random' | 'sequential';
  symbols: string[];
  timeframes: string[];
}

export interface Tournament {
  id: number;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  model: string;
  elimination_pct: number;
  images_phase_1: number;
  images_phase_2: number;
  images_phase_3: number;
  image_offset: number;
  selection_strategy: string;
  symbols_json: string;
  timeframes_json: string;
  started_at: string | null;
  completed_at: string | null;
  duration_sec: number | null;
  winner_prompt_name: string | null;
  winner_win_rate: number | null;
  winner_avg_pnl: number | null;
  total_api_calls: number;
  created_at: string;
}

export interface TournamentPrompt {
  id: number;
  tournament_id: number;
  prompt_name: string;
  status: 'active' | 'eliminated' | 'winner';
  eliminated_in_phase: number | null;
  final_rank: number | null;
  total_trades: number;
  total_wins: number;
  total_losses: number;
  total_holds: number;
  cumulative_pnl: number;
}

export interface PhaseResult {
  id: number;
  phase_id: number;
  tournament_prompt_id: number;
  prompt_name?: string;
  trades: number;
  wins: number;
  losses: number;
  holds: number;
  total_pnl: number;
  win_rate: number;
  avg_pnl: number;
  rank_in_phase: number | null;
  eliminated: boolean;
}

/**
 * Create a new tournament
 */
export function createTournament(config: TournamentConfig): number {
  const db = getDb();
  const result = db.prepare(`
    INSERT INTO tournaments (
      name, model, elimination_pct, images_phase_1, images_phase_2, images_phase_3,
      image_offset, selection_strategy, symbols_json, timeframes_json, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
  `).run(
    config.name,
    config.model,
    config.eliminationPct,
    config.imagesPhase1,
    config.imagesPhase2,
    config.imagesPhase3,
    config.imageOffset,
    config.selectionStrategy,
    JSON.stringify(config.symbols),
    JSON.stringify(config.timeframes)
  );
  return result.lastInsertRowid as number;
}

/**
 * Get tournament by ID
 */
export function getTournament(id: number): Tournament | null {
  const db = getDb();
  return db.prepare('SELECT * FROM tournaments WHERE id = ?').get(id) as Tournament | null;
}

/**
 * Get all tournaments (most recent first)
 */
export function getTournaments(limit = 20): Tournament[] {
  const db = getDb();
  return db.prepare('SELECT * FROM tournaments ORDER BY created_at DESC LIMIT ?').all(limit) as Tournament[];
}

/**
 * Update tournament status
 */
export function updateTournamentStatus(id: number, status: Tournament['status'], extra?: Partial<Tournament>): void {
  const db = getDb();
  let sql = 'UPDATE tournaments SET status = ?';
  const params: unknown[] = [status];
  
  if (extra) {
    if (extra.started_at) { sql += ', started_at = ?'; params.push(extra.started_at); }
    if (extra.completed_at) { sql += ', completed_at = ?'; params.push(extra.completed_at); }
    if (extra.duration_sec !== undefined) { sql += ', duration_sec = ?'; params.push(extra.duration_sec); }
    if (extra.winner_prompt_name) { sql += ', winner_prompt_name = ?'; params.push(extra.winner_prompt_name); }
    if (extra.winner_win_rate !== undefined) { sql += ', winner_win_rate = ?'; params.push(extra.winner_win_rate); }
    if (extra.winner_avg_pnl !== undefined) { sql += ', winner_avg_pnl = ?'; params.push(extra.winner_avg_pnl); }
    if (extra.total_api_calls !== undefined) { sql += ', total_api_calls = ?'; params.push(extra.total_api_calls); }
  }
  
  sql += ' WHERE id = ?';
  params.push(id);
  db.prepare(sql).run(...params);
}

/**
 * Add prompts to tournament
 */
export function addTournamentPrompts(tournamentId: number, promptNames: string[]): void {
  const db = getDb();
  const stmt = db.prepare('INSERT INTO tournament_prompts (tournament_id, prompt_name) VALUES (?, ?)');
  const insertMany = db.transaction((prompts: string[]) => {
    for (const name of prompts) stmt.run(tournamentId, name);
  });
  insertMany(promptNames);
}

/**
 * Get prompts for tournament
 */
export function getTournamentPrompts(tournamentId: number): TournamentPrompt[] {
  const db = getDb();
  return db.prepare('SELECT * FROM tournament_prompts WHERE tournament_id = ? ORDER BY final_rank, prompt_name')
    .all(tournamentId) as TournamentPrompt[];
}

/**
 * Get active prompts for tournament
 */
export function getActivePrompts(tournamentId: number): TournamentPrompt[] {
  const db = getDb();
  return db.prepare("SELECT * FROM tournament_prompts WHERE tournament_id = ? AND status = 'active'")
    .all(tournamentId) as TournamentPrompt[];
}

