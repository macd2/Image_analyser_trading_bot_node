import { NextRequest, NextResponse } from 'next/server'
import { spawn } from 'child_process'
import path from 'path'

/**
 * GET /api/bot/strategies
 * Returns list of available strategies from the Python backend
 */
export async function GET(request: NextRequest) {
  return new Promise((resolve) => {
    const pythonScript = path.join(process.cwd(), 'python', 'get_available_strategies.py')

    let output = ''
    let errorOutput = ''

    const pythonProcess = spawn('python3', [pythonScript], {
      cwd: process.cwd(),
      env: { ...process.env }
    })

    pythonProcess.stdout.on('data', (data) => {
      output += data.toString()
    })

    pythonProcess.stderr.on('data', (data) => {
      errorOutput += data.toString()
    })

    pythonProcess.on('close', (code) => {
      if (code !== 0) {
        console.error('Failed to get strategies:', errorOutput)
        return resolve(NextResponse.json(
          { error: 'Failed to get strategies', details: errorOutput },
          { status: 500 }
        ))
      }

      try {
        const strategies = JSON.parse(output)
        resolve(NextResponse.json({ strategies }))
      } catch (err) {
        console.error('Failed to parse strategies:', err)
        resolve(NextResponse.json(
          { error: 'Failed to parse strategies', details: String(err) },
          { status: 500 }
        ))
      }
    })
  })
}

