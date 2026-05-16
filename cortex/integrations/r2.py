"""
Cloudflare R2 client for downloading/uploading meeting insights, documents, templates.
Uses boto3 with R2 endpoint.
"""

import boto3
import json
import yaml
from typing import Optional, Dict, Any
import logging
from cortex.config import R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME

log = logging.getLogger("cortex.r2")

class R2Client:
    def __init__(self):
        """Initialize boto3 S3 client for R2"""
        if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
            log.warning("R2 credentials not fully configured. R2 operations may fail.")

        self.s3 = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto"
        )
        self.bucket = R2_BUCKET_NAME

    async def download_yaml(
        self,
        project_id: str,
        meeting_id: str,
        r2_key: str = None,
        date_str: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Download insights.yaml from R2.
        Path: projects/{project_id}/{YYYY-MM-DD}_{meeting_id}/insights.yaml by default,
        or use the explicit r2_key if provided.
        """
        try:
            if r2_key:
                key = r2_key
            else:
                # Construct path from meeting_id (format: mtg_YYYYMMDD_proj42_standup)
                # Extract date from meeting_id or use provided date_str
                if not date_str:
                    # Try to extract from meeting_id
                    parts = meeting_id.split("_")
                    if len(parts) >= 2:
                        date_str = parts[1]  # mtg_YYYYMMDD_...
                        date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                    else:
                        log.error(f"Cannot parse date from meeting_id: {meeting_id}")
                        return None

                key = f"projects/{project_id}/{date_str}_{meeting_id}/insights.yaml"
            log.info(f"Downloading {key} from R2")

            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            content = response["Body"].read().decode("utf-8")
            return yaml.safe_load(content)
        except Exception as e:
            log.error(f"Failed to download {key}: {e}")
            return None

    async def upload_yaml(
        self,
        project_id: str,
        meeting_id: str,
        content: Dict[str, Any],
        enriched: bool = False,
        date_str: str = None
    ) -> bool:
        """
        Upload insights.yaml or insights_enriched.yaml to R2.
        """
        try:
            if not date_str:
                parts = meeting_id.split("_")
                if len(parts) >= 2:
                    date_str = parts[1]
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            filename = "insights_enriched.yaml" if enriched else "insights.yaml"
            key = f"projects/{project_id}/{date_str}_{meeting_id}/{filename}"

            log.info(f"Uploading {key} to R2")
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=yaml.safe_dump(content).encode("utf-8"),
                ContentType="application/yaml"
            )
            return True
        except Exception as e:
            log.error(f"Failed to upload {key}: {e}")
            return False

    async def upload_document(
        self,
        project_id: str,
        doc_type: str,
        filename: str,
        content: bytes,
        version: str = "v1.0"
    ) -> Optional[str]:
        """
        Upload a document (SOW, architecture, timeline, generated doc, etc.) to R2.
        Returns: R2 key if successful, None otherwise.
        """
        try:
            # Determine folder based on doc_type
            if doc_type in ["sow", "solution_architecture", "timeline", "proposal"]:
                folder = "source-docs"
            elif doc_type in ["status_report", "milestone_deliverable", "kt_document", "onboarding_brief", "renewal_proposal"]:
                folder = "generated-docs"
            else:
                folder = "generated-docs"

            key = f"projects/{project_id}/{folder}/{filename}"
            log.info(f"Uploading document {key} to R2")

            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType="application/octet-stream"
            )
            return key
        except Exception as e:
            log.error(f"Failed to upload document: {e}")
            return None

    async def get_object(self, key: str) -> Optional[bytes]:
        """
        Generic S3 object download.
        """
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            log.error(f"Failed to download {key}: {e}")
            return None

    async def list_objects(self, prefix: str) -> list:
        """
        List objects in R2 with given prefix.
        """
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            return [obj["Key"] for obj in response.get("Contents", [])]
        except Exception as e:
            log.error(f"Failed to list objects with prefix {prefix}: {e}")
            return []

# Global instance
_r2_client: Optional[R2Client] = None

def get_r2_client() -> R2Client:
    """Get or create R2 client instance"""
    global _r2_client
    if _r2_client is None:
        _r2_client = R2Client()
    return _r2_client
