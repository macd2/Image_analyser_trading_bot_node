/**
 * Strategy Settings Schema API
 * GET /api/strategies/{strategy}/settings-schema
 * 
 * Returns the settings schema for a given strategy type.
 * Used by SettingsModal to dynamically show correct settings.
 */

import { NextRequest, NextResponse } from 'next/server';
import { spawn } from 'child_process';
import path from 'path';

export async function GET(
  request: NextRequest,
  { params }: { params: { strategy: string } }
) {
  const strategy = params.strategy;

  if (!strategy) {
    return NextResponse.json(
      { error: 'Strategy parameter is required' },
      { status: 400 }
    );
  }

  return new Promise((resolve) => {
    const pythonScript = path.join(
      process.cwd(),
      'python',
      'get_strategy_settings_schema.py'
    );

    let output = '';
    let errorOutput = '';

    const pythonProcess = spawn('python3', [pythonScript, strategy], {
      cwd: process.cwd(),
      env: { ...process.env },
    });

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        console.error(`Python script error for strategy ${strategy}:`, errorOutput);
        return resolve(
          NextResponse.json(
            { error: `Failed to get settings schema for strategy: ${strategy}` },
            { status: 500 }
          )
        );
      }

      try {
        const schema = JSON.parse(output);
        return resolve(
          NextResponse.json({
            strategy,
            schema,
          })
        );
      } catch (error) {
        console.error('Failed to parse Python output:', error);
        return resolve(
          NextResponse.json(
            { error: 'Failed to parse settings schema' },
            { status: 500 }
          )
        );
      }
    });
  });
}

