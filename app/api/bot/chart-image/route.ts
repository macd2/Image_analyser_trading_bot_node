/**
 * Chart Image API - Serves chart images from storage (local or Supabase)
 */

import { NextRequest, NextResponse } from 'next/server';
import path from 'path';
import { readFile, fileExists, getStorageType } from '@/lib/storage';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const chartPath = searchParams.get('path');

    if (!chartPath) {
      return NextResponse.json({ error: 'Chart path required' }, { status: 400 });
    }

    const storageType = getStorageType();
    console.log(`[Chart Image API] Fetching chart: ${chartPath} (storage: ${storageType})`);

    // Normalize path - remove leading "trading_bot/data/" or "data/" if present
    let normalizedPath = chartPath.replace(/^(trading_bot\/data\/|data\/)/, '');

    // Extract just the filename
    const filename = path.basename(chartPath);

    // Try multiple possible paths (in order of preference)
    const possiblePaths = [
      // Original path (e.g., "charts/SYMBOL_1h_DATE.png")
      normalizedPath,
      // Just filename in charts folder
      `charts/${filename}`,
      // .backup folder
      `charts/.backup/${filename}`,
    ];

    let imageBuffer: Buffer | null = null;
    let foundPath: string | null = null;

    // Try each path until we find the file
    for (const p of possiblePaths) {
      const exists = await fileExists(p);
      if (exists) {
        imageBuffer = await readFile(p);
        if (imageBuffer) {
          foundPath = p;
          break;
        }
      }
    }

    if (!imageBuffer || !foundPath) {
      console.error(`[Chart Image API] Chart not found: ${chartPath}`);
      return NextResponse.json({
        error: 'Chart image not found',
        tried: possiblePaths,
        storageType
      }, { status: 404 });
    }

    console.log(`[Chart Image API] Found chart at: ${foundPath}`);

    // Determine content type based on extension
    const ext = path.extname(foundPath).toLowerCase();
    const contentType = ext === '.png' ? 'image/png' : ext === '.jpg' || ext === '.jpeg' ? 'image/jpeg' : 'image/png';

    // Return image with proper headers
    // Set Content-Length explicitly to avoid header mismatch
    return new NextResponse(imageBuffer as any, {
      headers: {
        'Content-Type': contentType,
        'Content-Length': imageBuffer.length.toString(),
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

