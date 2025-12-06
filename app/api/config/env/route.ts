/**
 * Environment Config API - Returns DB and Storage type for UI display
 */

import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    db_type: process.env.DB_TYPE || 'sqlite',
    storage_type: process.env.STORAGE_TYPE || 'local',
  });
}

