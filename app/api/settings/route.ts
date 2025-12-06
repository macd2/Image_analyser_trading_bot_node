/**
 * Settings API - GET/POST/DELETE instance settings
 */

import { NextRequest, NextResponse } from 'next/server';
import { getSettings, saveSettings, deleteSettings, listInstances } from '@/lib/db/settings';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const instanceId = searchParams.get('instanceId');

  try {
    if (!instanceId) {
      // List all instances
      const instances = listInstances();
      return NextResponse.json({ instances });
    }

    const settings = getSettings(instanceId);
    return NextResponse.json({ instanceId, settings: settings || {} });
  } catch (error) {
    console.error('Settings GET error:', error);
    return NextResponse.json({ error: 'Failed to get settings' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { instanceId, settings } = body;

    if (!instanceId) {
      return NextResponse.json({ error: 'instanceId is required' }, { status: 400 });
    }

    saveSettings(instanceId, settings || {});
    return NextResponse.json({ success: true, instanceId });
  } catch (error) {
    console.error('Settings POST error:', error);
    return NextResponse.json({ error: 'Failed to save settings' }, { status: 500 });
  }
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const instanceId = searchParams.get('instanceId');

  if (!instanceId) {
    return NextResponse.json({ error: 'instanceId is required' }, { status: 400 });
  }

  try {
    const deleted = deleteSettings(instanceId);
    return NextResponse.json({ success: deleted, instanceId });
  } catch (error) {
    console.error('Settings DELETE error:', error);
    return NextResponse.json({ error: 'Failed to delete settings' }, { status: 500 });
  }
}

