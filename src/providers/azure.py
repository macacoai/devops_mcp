import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict

# Azure imports
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient

from src.utils import sanitize_python_code


def get_azure_credential():
    """
    Get Azure credentials using DefaultAzureCredential or specific credentials.

    This function follows the Azure SDK authentication patterns and supports multiple
    authentication methods including environment variables, Azure CLI, managed identity,
    and service principal authentication.

    Args:
        client_id (str, optional): Azure client ID (service principal)
        client_secret (str, optional): Azure client secret (service principal)
        tenant_id (str, optional): Azure tenant ID
        subscription_id (str, optional): Azure subscription ID

    Returns:
        tuple: (credential, subscription_id) where credential implements TokenCredential
    """
    # Get values from parameters or environment variables
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    tenant_id = os.getenv("AZURE_TENANT_ID")
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")

    # Create appropriate credential based on available information
    if client_id and client_secret and tenant_id:
        print("Using Azure service principal authentication")
        credential = ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
    else:
        print("Using Azure DefaultAzureCredential (supports CLI, managed identity, etc.)")
        # DefaultAzureCredential automatically tries multiple authentication methods:
        # 1. Environment variables
        # 2. Managed identity
        # 3. Azure CLI
        # 4. Azure PowerShell
        # 5. Interactive browser (if enabled)
        credential = DefaultAzureCredential()

    if not subscription_id:
        raise ValueError("Azure subscription ID is required. Set AZURE_SUBSCRIPTION_ID environment variable.")

    return credential, subscription_id


def get_azure_clients(credential, subscription_id):
    """
    Create Azure management clients for common services.

    Args:
        credential: Azure credential object
        subscription_id (str): Azure subscription ID

    Returns:
        dict: Dictionary of Azure service clients
    """
    return {
        "compute": ComputeManagementClient(credential, subscription_id),
        "storage": StorageManagementClient(credential, subscription_id),
        "resource": ResourceManagementClient(credential, subscription_id),
        "network": NetworkManagementClient(credential, subscription_id),
        "monitor": MonitorManagementClient(credential, subscription_id),
    }


async def azure_execute(
    code: str,
) -> Dict[str, Any]:
    try:
        # Get Azure credential and subscription ID
        credential, subscription_id = get_azure_credential()

        # Create Azure service clients
        clients = get_azure_clients(credential, subscription_id)

        # Build execution namespace
        namespace = {
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
            "credential": credential,
            "subscription_id": subscription_id,
            "compute_client": clients["compute"],
            "storage_client": clients["storage"],
            "resource_client": clients["resource"],
            "network_client": clients["network"],
            "monitor_client": clients["monitor"],
            # Also provide direct access to management client classes
            "ComputeManagementClient": ComputeManagementClient,
            "StorageManagementClient": StorageManagementClient,
            "ResourceManagementClient": ResourceManagementClient,
            "NetworkManagementClient": NetworkManagementClient,
            "MonitorManagementClient": MonitorManagementClient,
        }

        # Use asyncio.wait_for for timeout
        output_capture = StringIO()
        error_capture = StringIO()
        code = sanitize_python_code(code)
        print(f"Executing Azure code: {code[:100]}...")

        with redirect_stdout(output_capture), redirect_stderr(error_capture):
            # Execute with timeout
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, lambda: exec(code, namespace)),
                timeout=30,
            )

        output = output_capture.getvalue()
        errors = error_capture.getvalue()

        return {"success": True, "output": output, "errors": errors if errors else None}

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Code execution timed out after 30 seconds",
            "error_type": "TimeoutError",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }
