import { NextResponse } from 'next/server'
import { execSync } from 'child_process'
import path from 'path'

interface PromptInfo {
  name: string
  description: string
}

export async function GET() {
  try {
    // Get the python directory path
    const pythonDir = path.join(process.cwd(), 'python')

    // Call the Python prompt registry to get available prompts dynamically
    const result = execSync(
      'python3 -m trading_bot.core.prompts.prompt_registry list',
      {
        cwd: pythonDir,
        encoding: 'utf-8',
        timeout: 10000
      }
    )

    const prompts: PromptInfo[] = JSON.parse(result.trim())

    return NextResponse.json({
      success: true,
      prompts,
      default: 'get_analyzer_prompt_trade_playbook_v1'
    })
  } catch (error) {
    console.error('Error fetching prompts:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to fetch prompts', details: String(error) },
      { status: 500 }
    )
  }
}

