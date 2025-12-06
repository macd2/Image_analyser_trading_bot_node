#!/usr/bin/env python3
"""
Upload local chart images to Supabase Storage bucket.

Usage:
    python upload-to-supabase.py --dry-run           # See what would be uploaded
    python upload-to-supabase.py                     # Upload charts (excludes .backup)
    python upload-to-supabase.py --include-backup    # Include .backup folder
"""

import os
import sys
import argparse
from pathlib import Path
import mimetypes

# Supabase Storage uses S3-compatible API
try:
    import boto3
    from botocore.config import Config
except ImportError:
    print("Installing boto3...")
    os.system("pip install boto3")
    import boto3
    from botocore.config import Config

# Load environment from .env.local
def load_env():
    env_path = Path(__file__).parent.parent.parent / ".env.local"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

# Configuration
BUCKET_URL = os.environ.get('SUPABASE_BUCKET_URL', '')
BUCKET_NAME = os.environ.get('SUPABASE_BUCKET_NAME', 'chart_images')
ACCESS_KEY = os.environ.get('SUPABASE_BUCKET_ACCESS_ID', '')
SECRET_KEY = os.environ.get('SUPABASE_BUCKET_SECRET', '')
REGION = os.environ.get('SUPABASE_BUCKET_REGION', 'ap-northeast-2')

# Chart directories to upload
CHART_DIRS = [
    Path("/home/slicks/projects/^^Python/Analyse_Chart_Screenshot/trading_bot/data/charts"),
    Path("/home/slicks/projects/^^Python/Analyse_Chart_Screenshot/NextJsAppBot/V2/prototype/data/charts"),
]

def get_s3_client():
    """Create S3-compatible client for Supabase Storage"""
    # Extract endpoint from bucket URL
    # https://xxx.supabase.co/storage/v1 -> https://xxx.supabase.co/storage/v1/s3
    endpoint = BUCKET_URL.rstrip('/') + '/s3'
    
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name=REGION,
        config=Config(signature_version='s3v4')
    )

def get_content_type(filepath: Path) -> str:
    """Get MIME type for file"""
    mime_type, _ = mimetypes.guess_type(str(filepath))
    return mime_type or 'application/octet-stream'

def upload_file(s3_client, local_path: Path, bucket_key: str, dry_run: bool = False) -> bool:
    """Upload a single file to Supabase bucket"""
    if dry_run:
        print(f"  [DRY-RUN] Would upload: {bucket_key}")
        return True
    
    try:
        content_type = get_content_type(local_path)
        s3_client.upload_file(
            str(local_path),
            BUCKET_NAME,
            bucket_key,
            ExtraArgs={'ContentType': content_type}
        )
        return True
    except Exception as e:
        print(f"  ⚠️ Error uploading {bucket_key}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Upload charts to Supabase Storage')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be uploaded')
    parser.add_argument('--include-backup', action='store_true', help='Include .backup folder (default: skip)')
    args = parser.parse_args()

    if not ACCESS_KEY or not SECRET_KEY:
        print("❌ Missing SUPABASE_BUCKET_ACCESS_ID or SUPABASE_BUCKET_SECRET in .env.local")
        sys.exit(1)

    print("=" * 50)
    print("Chart Upload to Supabase Storage")
    print("=" * 50)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Endpoint: {BUCKET_URL}")
    print(f"Dry run: {args.dry_run}")
    print(f"Include .backup: {args.include_backup}")
    print()

    s3_client = get_s3_client()
    
    total_files = 0
    uploaded = 0
    
    for chart_dir in CHART_DIRS:
        if not chart_dir.exists():
            print(f"⚠️ Directory not found: {chart_dir}")
            continue
            
        print(f"📁 Scanning: {chart_dir}")
        
        for filepath in chart_dir.rglob("*.png"):
            # Build bucket key preserving folder structure
            relative_path = filepath.relative_to(chart_dir)

            # Skip .backup folder unless --include-backup is set
            if '.backup' in str(relative_path) and not args.include_backup:
                continue

            bucket_key = f"charts/{relative_path}"
            total_files += 1
            
            if upload_file(s3_client, filepath, bucket_key, args.dry_run):
                uploaded += 1
            
            # Progress indicator
            if total_files % 100 == 0:
                print(f"  ... processed {total_files} files")
    
    print()
    print(f"✅ {'Would upload' if args.dry_run else 'Uploaded'}: {uploaded}/{total_files} files")

if __name__ == "__main__":
    main()

