/**
 * Test database connection to diagnose the issue
 */

import { dbQuery } from './lib/db/trading-db';

async function testConnection() {
  console.log('Testing database connection...');
  console.log('DB_TYPE:', process.env.DB_TYPE);
  console.log('DATABASE_URL:', process.env.DATABASE_URL ? 'Set' : 'Not set');
  
  try {
    // Test simple query
    const result = await dbQuery('SELECT 1 as test');
    console.log('✅ Connection successful:', result);

    // List all tables
    const tables = await dbQuery(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);
    console.log('\n📋 Available tables:');
    tables.forEach((t: any) => console.log('  -', t.table_name));

    // Check if settings table exists
    const hasSettings = tables.some((t: any) => t.table_name === 'settings');
    console.log(`\n❓ Settings table exists: ${hasSettings}`);

    if (!hasSettings) {
      console.log('⚠️  Settings table is missing! Checking for app_settings...');
      const hasAppSettings = tables.some((t: any) => t.table_name === 'app_settings');
      console.log(`   app_settings exists: ${hasAppSettings}`);
    }

  } catch (error) {
    console.error('❌ Database error:', error);
    if (error instanceof Error) {
      console.error('Error message:', error.message);
      console.error('Error stack:', error.stack);
    }
  }
  
  process.exit(0);
}

testConnection();

