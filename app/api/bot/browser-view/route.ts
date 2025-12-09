import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

// Possible screenshot paths (newest first)
const SCREENSHOT_PATHS = [
  'data/charts/debug_watchlist.png',
  'data/charts/latest_chart.png',
];

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const checkOnly = searchParams.get('check') === 'true';

    // Find the first existing screenshot
    let screenshotPath: string | null = null;
    let stats: fs.Stats | null = null;

    for (const relativePath of SCREENSHOT_PATHS) {
      const fullPath = path.join(process.cwd(), relativePath);
      if (fs.existsSync(fullPath)) {
        screenshotPath = fullPath;
        stats = fs.statSync(fullPath);
        break;
      }
    }

    // Also check for any recent chart screenshots
    if (!screenshotPath) {
      const chartsDir = path.join(process.cwd(), 'data/charts');
      if (fs.existsSync(chartsDir)) {
        const files = fs.readdirSync(chartsDir)
          .filter(f => f.endsWith('.png'))
          .map(f => ({
            name: f,
            path: path.join(chartsDir, f),
            mtime: fs.statSync(path.join(chartsDir, f)).mtime
          }))
          .sort((a, b) => b.mtime.getTime() - a.mtime.getTime());

        if (files.length > 0) {
          screenshotPath = files[0].path;
          stats = fs.statSync(files[0].path);
        }
      }
    }

    if (!screenshotPath || !stats) {
      return NextResponse.json({
        available: false,
        error: 'No browser screenshot available. Start the bot to capture charts.',
        hint: 'The bot captures screenshots during trading cycles.'
      }, { status: 404 });
    }

    // Check mode - just return metadata
    if (checkOnly) {
      return NextResponse.json({
        available: true,
        path: screenshotPath,
        lastModified: stats.mtime.toISOString(),
        size: stats.size
      });
    }

    // Read and return the image
    const imageBuffer = fs.readFileSync(screenshotPath);

    return new NextResponse(imageBuffer, {
      headers: {
        'Content-Type': 'image/png',
        'Content-Length': imageBuffer.length.toString(),
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Last-Modified': stats.mtime.toISOString(),
        'X-Screenshot-Time': stats.mtime.toISOString(),
        'X-Screenshot-Path': path.basename(screenshotPath),
      },
    });
  } catch (error) {
    console.error('Error serving browser screenshot:', error);
    return NextResponse.json(
      { error: 'Failed to load browser screenshot' },
      { status: 500 }
    );
  }
}

