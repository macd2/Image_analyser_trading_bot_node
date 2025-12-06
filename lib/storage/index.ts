/**
 * Storage Abstraction Layer
 * 
 * Supports two modes based on STORAGE_TYPE env var:
 * - 'local': Filesystem storage (default for development)
 * - 'supabase': Supabase Storage (for production/Railway)
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';
import fs from 'fs';
import path from 'path';

export type StorageType = 'local' | 'supabase';

export interface StorageConfig {
  type: StorageType;
  localBasePath?: string;
  supabaseUrl?: string;
  supabaseKey?: string;
  bucketName?: string;
}

export interface UploadResult {
  success: boolean;
  path: string;
  url?: string;
  error?: string;
}

// Get storage type from environment
export function getStorageType(): StorageType {
  const type = process.env.STORAGE_TYPE || 'local';
  return type === 'supabase' ? 'supabase' : 'local';
}

// Get storage configuration from environment
export function getStorageConfig(): StorageConfig {
  const type = getStorageType();
  
  if (type === 'supabase') {
    return {
      type: 'supabase',
      supabaseUrl: process.env.SUPABASE_BUCKET_URL,
      supabaseKey: process.env.SUPABASE_BUCKET_SECRET,
      bucketName: process.env.SUPABASE_BUCKET_NAME || 'chart_images',
    };
  }
  
  return {
    type: 'local',
    localBasePath: path.join(process.cwd(), 'data', 'charts'),
  };
}

// Supabase client singleton
let supabaseClient: SupabaseClient | null = null;

function getSupabaseClient(): SupabaseClient {
  if (!supabaseClient) {
    const url = process.env.SUPABASE_BUCKET_URL?.replace('/storage/v1', '') || '';
    const key = process.env.SUPABASE_BUCKET_SECRET || '';
    supabaseClient = createClient(url, key);
  }
  return supabaseClient;
}

/**
 * Upload a file to storage
 */
export async function uploadFile(
  filePath: string,
  fileBuffer: Buffer,
  contentType: string = 'image/png'
): Promise<UploadResult> {
  const config = getStorageConfig();
  
  if (config.type === 'local') {
    return uploadLocal(filePath, fileBuffer, config.localBasePath!);
  } else {
    return uploadSupabase(filePath, fileBuffer, contentType, config.bucketName!);
  }
}

/**
 * Get a file from storage
 */
export async function getFile(filePath: string): Promise<Buffer | null> {
  const config = getStorageConfig();
  
  if (config.type === 'local') {
    return getFileLocal(filePath, config.localBasePath!);
  } else {
    return getFileSupabase(filePath, config.bucketName!);
  }
}

/**
 * Get public URL for a file
 */
export function getFileUrl(filePath: string): string {
  const config = getStorageConfig();
  
  if (config.type === 'local') {
    // Return API route for local files
    return `/api/charts/${encodeURIComponent(filePath)}`;
  } else {
    // Return Supabase public URL
    const baseUrl = process.env.SUPABASE_BUCKET_URL || '';
    return `${baseUrl}/object/public/${config.bucketName}/${filePath}`;
  }
}

/**
 * Check if file exists
 */
export async function fileExists(filePath: string): Promise<boolean> {
  const config = getStorageConfig();
  
  if (config.type === 'local') {
    const fullPath = path.join(config.localBasePath!, filePath);
    return fs.existsSync(fullPath);
  } else {
    const supabase = getSupabaseClient();
    const { data } = await supabase.storage
      .from(config.bucketName!)
      .list(path.dirname(filePath), { search: path.basename(filePath) });
    return (data?.length ?? 0) > 0;
  }
}

// Local storage implementations
function uploadLocal(filePath: string, buffer: Buffer, basePath: string): UploadResult {
  try {
    const fullPath = path.join(basePath, filePath);
    fs.mkdirSync(path.dirname(fullPath), { recursive: true });
    fs.writeFileSync(fullPath, buffer);
    return { success: true, path: filePath, url: `/api/charts/${filePath}` };
  } catch (error) {
    return { success: false, path: filePath, error: String(error) };
  }
}

function getFileLocal(filePath: string, basePath: string): Buffer | null {
  const fullPath = path.join(basePath, filePath);
  if (!fs.existsSync(fullPath)) return null;
  return fs.readFileSync(fullPath);
}

// Supabase storage implementations
async function uploadSupabase(
  filePath: string, buffer: Buffer, contentType: string, bucket: string
): Promise<UploadResult> {
  const supabase = getSupabaseClient();
  const { error } = await supabase.storage.from(bucket).upload(filePath, buffer, {
    contentType, upsert: true
  });
  if (error) return { success: false, path: filePath, error: error.message };
  return { success: true, path: filePath, url: getFileUrl(filePath) };
}

async function getFileSupabase(filePath: string, bucket: string): Promise<Buffer | null> {
  const supabase = getSupabaseClient();
  const { data, error } = await supabase.storage.from(bucket).download(filePath);
  if (error || !data) return null;
  return Buffer.from(await data.arrayBuffer());
}

/**
 * Move a file to a new location (for backup functionality)
 */
export async function moveFile(
  sourcePath: string,
  destPath: string
): Promise<{ success: boolean; error?: string }> {
  const config = getStorageConfig();

  if (config.type === 'local') {
    return moveFileLocal(sourcePath, destPath, config.localBasePath!);
  } else {
    return moveFileSupabase(sourcePath, destPath, config.bucketName!);
  }
}

function moveFileLocal(
  sourcePath: string,
  destPath: string,
  basePath: string
): { success: boolean; error?: string } {
  try {
    const fullSource = path.join(basePath, sourcePath);
    const fullDest = path.join(basePath, destPath);

    if (!fs.existsSync(fullSource)) {
      return { success: false, error: 'Source file not found' };
    }

    // Create destination directory
    fs.mkdirSync(path.dirname(fullDest), { recursive: true });
    fs.renameSync(fullSource, fullDest);
    return { success: true };
  } catch (error) {
    return { success: false, error: String(error) };
  }
}

async function moveFileSupabase(
  sourcePath: string,
  destPath: string,
  bucket: string
): Promise<{ success: boolean; error?: string }> {
  const supabase = getSupabaseClient();

  // Supabase doesn't have native move, so: copy then delete
  const { error: moveError } = await supabase.storage
    .from(bucket)
    .move(sourcePath, destPath);

  if (moveError) {
    return { success: false, error: moveError.message };
  }

  return { success: true };
}

/**
 * Delete a file from storage
 */
export async function deleteFile(filePath: string): Promise<{ success: boolean; error?: string }> {
  const config = getStorageConfig();

  if (config.type === 'local') {
    try {
      const fullPath = path.join(config.localBasePath!, filePath);
      if (fs.existsSync(fullPath)) {
        fs.unlinkSync(fullPath);
      }
      return { success: true };
    } catch (error) {
      return { success: false, error: String(error) };
    }
  } else {
    const supabase = getSupabaseClient();
    const { error } = await supabase.storage.from(config.bucketName!).remove([filePath]);
    if (error) return { success: false, error: error.message };
    return { success: true };
  }
}

/**
 * List files in a directory
 */
export async function listFiles(dirPath: string): Promise<string[]> {
  const config = getStorageConfig();

  if (config.type === 'local') {
    const fullPath = path.join(config.localBasePath!, dirPath);
    if (!fs.existsSync(fullPath)) return [];
    return fs.readdirSync(fullPath).filter(f => !f.startsWith('.'));
  } else {
    const supabase = getSupabaseClient();
    const { data, error } = await supabase.storage.from(config.bucketName!).list(dirPath);
    if (error || !data) return [];
    return data.map(f => f.name);
  }
}

