import os
from google.cloud import storage
import json
import traceback
import config
from urllib.parse import urlparse


def list_gcs_children(uri: str) -> list:
    """
    List immediate children of a GCS path.

    Args:
        uri (str): GCS path in format gs://bucket_name/prefix/

    Returns:
        list: Immediate child paths under the given GCS path.
    """
    if not uri.startswith("gs://"):
        raise ValueError("GCS URI must start with 'gs://'")

    # Parse bucket and prefix
    path_parts = uri[5:].split("/", 1)
    bucket_name = path_parts[0]
    prefix = path_parts[1] if len(path_parts) > 1 else ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    # list blobs with delimiter to get only immediate children
    blobs = client.list_blobs(bucket, prefix=prefix, delimiter="/")

    # Immediate files
    files = [blob.name for blob in blobs]

    # Immediate "folders" (prefixes)
    folders = list(blobs.prefixes)
    
    res_files = files + folders
    res_files = [f"gs://{bucket_name}/" + i   for i in res_files]
    return res_files

def write_status(file_name :str, value :dict):
    write_or_update_json_to_gcs(config.BUCKET, f"status/{file_name}", value)

def write_text_to_gcs(blob_name: str, text_content: str):
    bucket_name = config.BUCKET
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        blob.upload_from_string(text_content, content_type="text/plain")
        
        print(f"✅ Successfully wrote text to gs://{bucket_name}/{blob_name}")
    
    except Exception as e:
        print(f"❌ Error writing text to GCS: {e}")
        
def write_json_to_gcs(blob_uri: str, json_data: dict | list):
    try:
        # Parse bucket and blob name from full URI
        if not blob_uri.startswith("gs://"):
            raise ValueError("blob_uri must start with 'gs://'")
        
        parts = blob_uri[5:].split("/", 1)
        if len(parts) != 2:
            raise ValueError("Invalid GCS URI format. Expected 'gs://bucket_name/path/to/blob'")
        
        bucket_name, blob_name = parts

        # Init GCS client
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Serialize dict/list to JSON
        json_string = json.dumps(json_data, indent=2)

        # Upload to GCS
        blob.upload_from_string(json_string, content_type="application/json")
        
        print(f"✅ Successfully wrote JSON to {blob_uri}")
        return True

    except Exception as e:
        print(f"❌ Error writing JSON to GCS: {e}")
        traceback.print_exc()
        return False
        
def read_text_from_gcs(gcs_uri: str) -> str:

    try:
        # Parse bucket and blob from URI
        parsed = urlparse(gcs_uri)
        if parsed.scheme != "gs":
            raise ValueError("Invalid GCS URI, must start with gs://")
        
        bucket_name = parsed.netloc
        blob_name = parsed.path.lstrip("/")

        # Initialize client and read blob
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        text_content = blob.download_as_text()

        print(f"✅ Successfully read text from {gcs_uri}")
        return text_content
    
    except Exception as e:
        print(f"❌ Error reading text from GCS ({gcs_uri}): {e}")
        return ""
    
def read_json_from_gcs(blob_name: str) -> dict | list:
    bucket_name = config.BUCKET
    
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Download the blob's content as a string
        json_string = blob.download_as_text()
        
        # Deserialize the JSON string into a Python object
        json_data = json.loads(json_string)
        
        print(f"✅ Successfully read JSON from gs://{bucket_name}/{blob_name}")
        return json_data
    
    except Exception as e:
        print(f"❌ Error reading JSON from GCS: {e}")
        return None
    
    
def write_or_update_json_to_gcs(blob_name: str, update_data: dict):
    bucket_name = config.BUCKET
    
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Try to download existing JSON content
        if blob.exists():
            current_data = json.loads(blob.download_as_string())
        else:
            current_data = {}

        # Update non-empty values only
        for key, value in update_data.items():
            if value != "":
                current_data[key] = value

        # Upload updated JSON
        blob.upload_from_string(
            json.dumps(current_data, indent=2),
            content_type="application/json"
        )

    except Exception as e:
        return str(e)