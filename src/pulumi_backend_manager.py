"""
Pulumi Backend Manager
Handles automatic creation and management of Pulumi backends
"""

import os
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import boto3
import botocore


class PulumiBackendManager:
    """Manages Pulumi backend creation and configuration"""

    def __init__(self, aws_session: Optional[boto3.Session] = None, debug: bool = False):
        self.aws_session = aws_session or boto3.Session()
        self.debug = debug

    def setup_backend(self, backend_url: str, auto_create: bool = True) -> Dict[str, Any]:
        """
        Setup Pulumi backend, creating it if necessary and requested

        Args:
            backend_url: Backend URL (s3://bucket, file:///path, etc.)
            auto_create: Whether to auto-create the backend if it doesn't exist

        Returns:
            Dict with setup result and information
        """
        if not backend_url:
            return {
                "success": True,
                "backend_type": "pulumi_cloud",
                "message": "Using Pulumi Cloud (default backend)",
                "created": False,
            }

        backend_type = self._detect_backend_type(backend_url)

        if self.debug:
            print(f"🔧 Setting up Pulumi backend: {backend_url}")
            print(f"📋 Backend type: {backend_type}")

        if backend_type == "s3":
            return self._setup_s3_backend(backend_url, auto_create)
        elif backend_type == "file":
            return self._setup_file_backend(backend_url, auto_create)
        elif backend_type == "azblob":
            return self._setup_azure_backend(backend_url, auto_create)
        elif backend_type == "gs":
            return self._setup_gcs_backend(backend_url, auto_create)
        else:
            return {
                "success": False,
                "error": f"Unsupported backend type: {backend_type}",
                "backend_type": backend_type,
            }

    def _detect_backend_type(self, backend_url: str) -> str:
        """Detect the type of backend from URL"""
        if backend_url.startswith("s3://"):
            return "s3"
        elif backend_url.startswith("file://") or backend_url.startswith("/"):
            return "file"
        elif backend_url.startswith("azblob://"):
            return "azblob"
        elif backend_url.startswith("gs://"):
            return "gs"
        elif backend_url.startswith("https://") and "blob.core.windows.net" in backend_url:
            return "azblob"
        else:
            return "unknown"

    def _setup_s3_backend(self, backend_url: str, auto_create: bool) -> Dict[str, Any]:
        """Setup S3 backend for Pulumi state storage"""
        try:
            # Parse S3 URL
            parsed = urlparse(backend_url)
            bucket_name = parsed.netloc
            prefix = parsed.path.lstrip("/") if parsed.path else ""

            if self.debug:
                print(f"🪣 S3 Backend - Bucket: {bucket_name}, Prefix: {prefix}")

            s3_client = self.aws_session.client("s3")

            # Check if bucket exists
            try:
                s3_client.head_bucket(Bucket=bucket_name)
                bucket_exists = True
                if self.debug:
                    print(f"✅ S3 bucket '{bucket_name}' already exists")
            except botocore.exceptions.ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code == "404":
                    bucket_exists = False
                    if self.debug:
                        print(f"❌ S3 bucket '{bucket_name}' does not exist")
                else:
                    return {"success": False, "error": f"Error checking S3 bucket: {str(e)}", "backend_type": "s3"}

            # Create bucket if it doesn't exist and auto_create is enabled
            if not bucket_exists and auto_create:
                try:
                    region = self.aws_session.region_name or "us-east-1"

                    # Create bucket
                    if region == "us-east-1":
                        # us-east-1 doesn't need LocationConstraint
                        s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        s3_client.create_bucket(
                            Bucket=bucket_name, CreateBucketConfiguration={"LocationConstraint": region}
                        )

                    # Enable versioning (recommended for state storage)
                    s3_client.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"})

                    # Add encryption
                    s3_client.put_bucket_encryption(
                        Bucket=bucket_name,
                        ServerSideEncryptionConfiguration={
                            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
                        },
                    )

                    if self.debug:
                        print(f"✅ Created S3 bucket '{bucket_name}' with versioning and encryption")

                    return {
                        "success": True,
                        "backend_type": "s3",
                        "bucket_name": bucket_name,
                        "region": region,
                        "created": True,
                        "message": f"S3 backend bucket '{bucket_name}' created successfully",
                        "features": ["versioning", "encryption"],
                    }

                except botocore.exceptions.ClientError as e:
                    return {
                        "success": False,
                        "error": f"Failed to create S3 bucket '{bucket_name}': {str(e)}",
                        "backend_type": "s3",
                    }

            elif not bucket_exists and not auto_create:
                return {
                    "success": False,
                    "error": f"S3 bucket '{bucket_name}' does not exist and auto-creation is disabled",
                    "backend_type": "s3",
                    "suggestion": "Enable auto-creation with --auto-create-pulumi-backend flag",
                }

            else:
                # Bucket exists
                return {
                    "success": True,
                    "backend_type": "s3",
                    "bucket_name": bucket_name,
                    "created": False,
                    "message": f"Using existing S3 bucket '{bucket_name}'",
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error setting up S3 backend: {str(e)}",
                "backend_type": "s3",
            }

    def _setup_file_backend(self, backend_url: str, auto_create: bool) -> Dict[str, Any]:
        """Setup local filesystem backend for Pulumi state storage"""
        try:
            # Parse file URL
            if backend_url.startswith("file://"):
                path = backend_url[7:]  # Remove file:// prefix
            else:
                path = backend_url

            # Expand user home directory
            path = os.path.expanduser(path)

            if self.debug:
                print(f"📁 File Backend - Path: {path}")

            # Check if directory exists
            if os.path.exists(path):
                if not os.path.isdir(path):
                    return {
                        "success": False,
                        "error": f"Backend path '{path}' exists but is not a directory",
                        "backend_type": "file",
                    }

                if self.debug:
                    print(f"✅ Directory '{path}' already exists")

                return {
                    "success": True,
                    "backend_type": "file",
                    "path": path,
                    "created": False,
                    "message": f"Using existing directory '{path}'",
                }

            # Create directory if auto_create is enabled
            if auto_create:
                try:
                    os.makedirs(path, mode=0o755, exist_ok=True)

                    if self.debug:
                        print(f"✅ Created directory '{path}'")

                    return {
                        "success": True,
                        "backend_type": "file",
                        "path": path,
                        "created": True,
                        "message": f"Created local backend directory '{path}'",
                    }

                except OSError as e:
                    return {
                        "success": False,
                        "error": f"Failed to create directory '{path}': {str(e)}",
                        "backend_type": "file",
                    }
            else:
                return {
                    "success": False,
                    "error": f"Backend directory '{path}' does not exist and auto-creation is disabled",
                    "backend_type": "file",
                    "suggestion": "Enable auto-creation with --auto-create-pulumi-backend flag",
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Unexpected error setting up file backend: {str(e)}",
                "backend_type": "file",
            }

    def _setup_azure_backend(self, backend_url: str, auto_create: bool) -> Dict[str, Any]:
        """Setup Azure Blob Storage backend (placeholder implementation)"""
        return {
            "success": False,
            "error": "Azure Blob Storage backend auto-creation not yet implemented",
            "backend_type": "azblob",
            "suggestion": "Please create the Azure storage container manually or use S3/file backends",
        }

    def _setup_gcs_backend(self, backend_url: str, auto_create: bool) -> Dict[str, Any]:
        """Setup Google Cloud Storage backend (placeholder implementation)"""
        return {
            "success": False,
            "error": "Google Cloud Storage backend auto-creation not yet implemented",
            "backend_type": "gs",
            "suggestion": "Please create the GCS bucket manually or use S3/file backends",
        }

    def validate_backend_access(self, backend_url: str) -> Dict[str, Any]:
        """
        Validate that the backend is accessible and properly configured

        Args:
            backend_url: Backend URL to validate

        Returns:
            Dict with validation result
        """
        backend_type = self._detect_backend_type(backend_url)

        if backend_type == "s3":
            return self._validate_s3_access(backend_url)
        elif backend_type == "file":
            return self._validate_file_access(backend_url)
        else:
            return {"success": False, "error": f"Backend validation not implemented for type: {backend_type}"}

    def _validate_s3_access(self, backend_url: str) -> Dict[str, Any]:
        """Validate S3 backend access"""
        try:
            parsed = urlparse(backend_url)
            bucket_name = parsed.netloc

            s3_client = self.aws_session.client("s3")

            # Try to list objects (read access)
            s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)

            # Try to put a test object (write access)
            test_key = ".pulumi/test-access"
            s3_client.put_object(Bucket=bucket_name, Key=test_key, Body=b"test")

            # Clean up test object
            s3_client.delete_object(Bucket=bucket_name, Key=test_key)

            return {"success": True, "message": f"S3 backend '{bucket_name}' is accessible with read/write permissions"}

        except Exception as e:
            return {"success": False, "error": f"S3 backend validation failed: {str(e)}"}

    def _validate_file_access(self, backend_url: str) -> Dict[str, Any]:
        """Validate file backend access"""
        try:
            if backend_url.startswith("file://"):
                path = backend_url[7:]
            else:
                path = backend_url

            path = os.path.expanduser(path)

            if not os.path.exists(path):
                return {"success": False, "error": f"Backend directory '{path}' does not exist"}

            if not os.path.isdir(path):
                return {"success": False, "error": f"Backend path '{path}' is not a directory"}

            # Test write access
            test_file = os.path.join(path, ".pulumi-test")
            try:
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
            except Exception as e:
                return {"success": False, "error": f"Backend directory '{path}' is not writable: {str(e)}"}

            return {"success": True, "message": f"File backend '{path}' is accessible with read/write permissions"}

        except Exception as e:
            return {"success": False, "error": f"File backend validation failed: {str(e)}"}
