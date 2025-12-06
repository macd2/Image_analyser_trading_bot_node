/**
 * Storage Abstraction Layer for Next.js/TypeScript
 * 
 * Supports two modes based on STORAGE_TYPE env var:
 * - 'local': Filesystem storage (default for development)
 * - 'supabase': Supabase Storage (for production)
 */

import fs from 'fs';
import path from 'path';
import { createClient } from '@supabase/supabase-js';

export type StorageType = 'local' | 'supabase';

export function getStorageType(): StorageType {
  const type = process.env.STORAGE_TYPE || 'local';
  return type as StorageType;
}

export function getLocalBasePath(): string {
  return path.join(process.cwd(), 'data', 'charts');
}

let supabaseClient: ReturnType<typeof createClient> | null = null;

export function getSupabaseClient() {
  if (supabaseClient) {
    return supabaseClient;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!supabaseUrl || !supabaseKey) {
    throw new Error('Supabase credentials not configured');
  }

  supabaseClient = createClient(supabaseUrl, supabaseKey);
  return supabaseClient;
}

export function getBucketName(): string {
  return process.env.SUPABASE_BUCKET_NAME || 'chart_images';
}

export async function readFile(filePath: string): Promise<Buffer | null> {
  const storageType = getStorageType();

  if (storageType === 'local') {
    try {
      const fullPath = path.join(getLocalBasePath(), filePath);
      if (!fs.existsSync(fullPath)) {
        return null;
      }
      return fs.readFileSync(fullPath);
    } catch (error) {
      console.error('Local read error:', error);
      return null;
    }
  } else {
    try {
      const supabase = getSupabaseClient();
      const bucket = getBucketName();
      
      const { data, error } = await supabase.storage
        .from(bucket)
        .download(filePath);

      if (error) {
        console.error('Supabase read error:', error);
        return null;
      }

      const arrayBuffer = await data.arrayBuffer();
      return Buffer.from(arrayBuffer);
    } catch (error) {
      console.error('Supabase read error:', error);
      return null;
    }
  }
}

export async function fileExists(filePath: string): Promise<boolean> {
  const storageType = getStorageType();

  if (storageType === 'local') {
    const fullPath = path.join(getLocalBasePath(), filePath);
    return fs.existsSync(fullPath);
  } else {
    try {
      const supabase = getSupabaseClient();
      const bucket = getBucketName();
      
      const { data, error } = await supabase.storage
        .from(bucket)
        .list(path.dirname(filePath), {
          search: path.basename(filePath)
        });

      if (error) {
        return false;
      }

      return data && data.length > 0;
    } catch (error) {
      return false;
    }
  }
}

export async function getPublicUrl(filePath: string): Promise<string | null> {
  const storageType = getStorageType();

  if (storageType === 'local') {
    // For local storage, return API route
    return `/api/bot/chart-image?path=${encodeURIComponent(filePath)}`;
  } else {
    try {
      const supabase = getSupabaseClient();
      const bucket = getBucketName();
      
      const { data } = supabase.storage
        .from(bucket)
        .getPublicUrl(filePath);

      return data.publicUrl;
    } catch (error) {
      console.error('Error getting public URL:', error);
      return null;
    }
  }
}

