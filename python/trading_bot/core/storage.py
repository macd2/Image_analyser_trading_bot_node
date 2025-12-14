"""
Storage Abstraction Layer for Python

Supports two modes based on STORAGE_TYPE env var:
- 'local': Filesystem storage (default for development)
- 'supabase': Supabase Storage via S3 protocol (for production)
"""

import os
import logging
from pathlib import Path
from typing import Optional, List
from dotenv import load_dotenv

# Load .env.local
env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

logger = logging.getLogger(__name__)

# S3 client singleton
_s3_client = None


def get_storage_type() -> str:
    """Get storage type from environment."""
    return os.getenv('STORAGE_TYPE', 'local')


def get_local_base_path() -> Path:
    """Get local base path for charts."""
    return Path(__file__).parent.parent.parent.parent / 'data' / 'charts'


def get_s3_client():
    """Get S3 client for Supabase storage (S3-compatible)."""
    global _s3_client
    if _s3_client:
        return _s3_client

    try:
        import boto3
        from botocore.config import Config

        # Supabase S3-compatible endpoint
        bucket_url = os.getenv('SUPABASE_BUCKET_URL', '')
        region = os.getenv('SUPABASE_BUCKET_REGION', 'ap-northeast-2')
        access_id = os.getenv('SUPABASE_BUCKET_ACCESS_ID', '')
        secret_key = os.getenv('SUPABASE_BUCKET_SECRET', '')

        if not bucket_url or not access_id or not secret_key:
            raise ValueError("Missing Supabase S3 credentials in environment variables")

        # Extract base URL (remove /storage/v1)
        endpoint_url = bucket_url.replace('/storage/v1', '/storage/v1/s3')

        _s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_id,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4')
        )
        return _s3_client
    except ImportError as e:
        logger.error(f"boto3 import failed: {e}. Install with: pip install boto3")
        raise ImportError("boto3 package required: pip install boto3") from e
    except Exception as e:
        logger.error(f"Failed to initialize S3 client: {e}")
        raise


def get_bucket_name() -> str:
    """Get Supabase bucket name."""
    return os.getenv('SUPABASE_BUCKET_NAME', 'chart_images')


def file_exists(file_path: str) -> bool:
    """Check if file exists in storage."""
    storage_type = get_storage_type()

    if storage_type == 'local':
        full_path = get_local_base_path() / file_path
        return full_path.exists()
    else:
        try:
            s3 = get_s3_client()
            bucket = get_bucket_name()
            s3.head_object(Bucket=bucket, Key=file_path)
            return True
        except Exception:
            return False


def move_file(source_path: str, dest_path: str) -> dict:
    """Move a file to a new location (for backup functionality)."""
    storage_type = get_storage_type()

    if storage_type == 'local':
        return _move_file_local(source_path, dest_path)
    else:
        return _move_file_s3(source_path, dest_path)


def _move_file_local(source_path: str, dest_path: str) -> dict:
    """Move file on local filesystem."""
    try:
        base = get_local_base_path()
        full_source = base / source_path
        full_dest = base / dest_path

        if not full_source.exists():
            return {'success': False, 'error': 'Source file not found'}

        # Create destination directory
        full_dest.parent.mkdir(parents=True, exist_ok=True)
        full_source.rename(full_dest)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _move_file_s3(source_path: str, dest_path: str) -> dict:
    """Move file in S3 bucket (copy + delete)."""
    try:
        s3 = get_s3_client()
        bucket = get_bucket_name()

        # First verify source file exists
        try:
            s3.head_object(Bucket=bucket, Key=source_path)
        except Exception:
            return {'success': False, 'error': f'Source file not found: {source_path}'}

        # S3 doesn't have native move - copy then delete
        copy_source = {'Bucket': bucket, 'Key': source_path}
        copy_response = s3.copy_object(Bucket=bucket, Key=dest_path, CopySource=copy_source)

        # Check if copy was successful
        if copy_response.get('ResponseMetadata', {}).get('HTTPStatusCode') != 200:
            return {'success': False, 'error': f'Copy failed with status {copy_response.get("ResponseMetadata", {}).get("HTTPStatusCode")}'}

        # Verify destination file exists before deleting source
        try:
            s3.head_object(Bucket=bucket, Key=dest_path)
        except Exception:
            return {'success': False, 'error': f'Destination file not created after copy: {dest_path}'}

        # Now delete the source
        s3.delete_object(Bucket=bucket, Key=source_path)

        # Verify source was deleted
        try:
            s3.head_object(Bucket=bucket, Key=source_path)
            return {'success': False, 'error': f'Source file still exists after delete: {source_path}'}
        except Exception:
            # Good - source is deleted
            pass

        logger.info(f"✅ Successfully moved {source_path} → {dest_path}")
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def list_files(dir_path: str) -> List[str]:
    """List files in a directory."""
    storage_type = get_storage_type()

    if storage_type == 'local':
        full_path = get_local_base_path() / dir_path
        if not full_path.exists():
            return []
        return [f.name for f in full_path.iterdir() if f.is_file() and not f.name.startswith('.')]
    else:
        try:
            s3 = get_s3_client()
            bucket = get_bucket_name()
            prefix = dir_path.rstrip('/') + '/' if dir_path else ''
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, Delimiter='/')

            files = []
            # Get files
            for obj in response.get('Contents', []):
                key = obj['Key']
                name = key[len(prefix):] if prefix else key
                if name and '/' not in name:  # Only direct children
                    files.append(name)
            # Get folders
            for prefix_obj in response.get('CommonPrefixes', []):
                folder = prefix_obj['Prefix'][len(prefix):].rstrip('/')
                if folder:
                    files.append(folder)
            return files
        except ImportError as e:
            error_msg = f"list_files error: boto3 not installed - {e}"
            logger.error(error_msg)
            return []
        except Exception as e:
            error_msg = f"list_files error: {type(e).__name__}: {e}"
            logger.error(error_msg)
            return []


def delete_file(file_path: str) -> dict:
    """Delete a file from storage."""
    storage_type = get_storage_type()

    if storage_type == 'local':
        try:
            full_path = get_local_base_path() / file_path
            if full_path.exists():
                full_path.unlink()
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    else:
        try:
            s3 = get_s3_client()
            bucket = get_bucket_name()
            s3.delete_object(Bucket=bucket, Key=file_path)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}


def save_file(file_path: str, data: bytes, content_type: str = 'image/png') -> dict:
    """
    Save file to storage (local or S3/Supabase).

    Args:
        file_path: Relative path within the storage (e.g., 'charts/BTCUSDT_1h_20241205.png')
        data: File content as bytes
        content_type: MIME type of the file

    Returns:
        dict with 'success' and optionally 'path' or 'error'
    """
    storage_type = get_storage_type()

    if storage_type == 'local':
        try:
            full_path = get_local_base_path() / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(data)
            logger.info(f"Saved file locally: {full_path}")
            return {'success': True, 'path': str(full_path)}
        except Exception as e:
            logger.error(f"Local save error: {e}")
            return {'success': False, 'error': str(e)}
    else:
        try:
            s3 = get_s3_client()
            bucket = get_bucket_name()
            s3.put_object(
                Bucket=bucket,
                Key=file_path,
                Body=data,
                ContentType=content_type
            )
            logger.info(f"Saved file to S3: {bucket}/{file_path}")
            return {'success': True, 'path': f"s3://{bucket}/{file_path}"}
        except ImportError as e:
            error_msg = f"S3 save error: boto3 not installed - {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}
        except Exception as e:
            error_msg = f"S3 save error: {type(e).__name__}: {e}"
            logger.error(error_msg)
            return {'success': False, 'error': error_msg}


def read_file(file_path: str) -> Optional[bytes]:
    """
    Read file from storage (local or S3/Supabase).

    Args:
        file_path: Relative path within the storage

    Returns:
        File content as bytes, or None if not found
    """
    storage_type = get_storage_type()

    if storage_type == 'local':
        try:
            full_path = get_local_base_path() / file_path
            if not full_path.exists():
                return None
            return full_path.read_bytes()
        except Exception as e:
            logger.error(f"Local read error: {e}")
            return None
    else:
        try:
            s3 = get_s3_client()
            bucket = get_bucket_name()
            response = s3.get_object(Bucket=bucket, Key=file_path)
            return response['Body'].read()
        except Exception as e:
            logger.error(f"S3 read error: {e}")
            return None


def get_public_url(file_path: str) -> Optional[str]:
    """
    Get public URL for a file (for serving to frontend).

    Args:
        file_path: Relative path within the storage

    Returns:
        Public URL or None if not available
    """
    storage_type = get_storage_type()

    if storage_type == 'local':
        # For local files, return a relative API path
        return f"/api/charts/{file_path}"
    else:
        # For Supabase, generate public URL
        bucket_url = os.getenv('SUPABASE_BUCKET_URL', '')
        bucket_name = get_bucket_name()
        # Supabase public URL format
        return f"{bucket_url}/object/public/{bucket_name}/{file_path}"

