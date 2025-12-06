/**
 * Chart Image API - Serves chart images from charts folder or .backup folder
 */

import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const chartPath = searchParams.get('path');

    if (!chartPath) {
      return NextResponse.json({ error: 'Chart path required' }, { status: 400 });
    }

    // Base directory - chart_path in DB is like "data/charts/SYMBOL_1h_DATE.png"
    const dataDir = path.join(process.cwd(), 'data');

    // Remove leading "trading_bot/" or "data/" if present, then build full path
    const normalizedPath = chartPath.replace(/^(trading_bot\/data|data)\//, '');
    const fullPath = path.join(dataDir, normalizedPath);

    // Extract just the filename for .backup lookup
    const filename = path.basename(chartPath);
    const chartsDir = path.join(dataDir, 'charts');

    // Try multiple possible paths
    const possiblePaths = [
      // Original path from database
      fullPath,
      // .backup folder (direct)
      path.join(chartsDir, '.backup', filename),
      // Current charts folder
      path.join(chartsDir, filename),
    ];

    let imagePath: string | null = null;
    for (const p of possiblePaths) {
      if (fs.existsSync(p)) {
        imagePath = p;
        break;
      }
    }

    if (!imagePath) {
      return NextResponse.json({
        error: 'Chart image not found',
        tried: possiblePaths.map(p => p.replace(dataDir, ''))
      }, { status: 404 });
    }

    // Read the image file
    const imageBuffer = fs.readFileSync(imagePath);
    
    // Determine content type based on extension
    const ext = path.extname(imagePath).toLowerCase();
    const contentType = ext === '.png' ? 'image/png' : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' : 'image/png';

    // Return image with proper headers
    return new NextResponse(imageBuffer, {
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });

  } catch (error) {
    console.error('Chart image error:', error);
    return NextResponse.json({
      error: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}

