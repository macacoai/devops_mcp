import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict

# Azure imports
from azure.identity import DefaultAzureCredential, ClientSecretCredential, AzureCliCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient


def get_azure_credential(client_id=None, client_secret=None, tenant_id=None, subscription_id=None):
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
    client_id = client_id or os.getenv("AZURE_CLIENT_ID")
    client_secret = client_secret or os.getenv("AZURE_CLIENT_SECRET")
    tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID")
    subscription_id = subscription_id or os.getenv("AZURE_SUBSCRIPTION_ID")

    # Create appropriate credential based on available information
    if client_id and client_secret and tenant_id:
        print("Using Azure service principal authentication")
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
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
        raise ValueError(
            "Azure subscription ID is required. Set AZURE_SUBSCRIPTION_ID environment variable or provide subscription_id parameter.")

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
        azure_client_id: str = None,
        azure_client_secret: str = None,
        azure_tenant_id: str = None,
        azure_subscription_id: str = None,
        sanitize_python_code=None,
) -> Dict[str, Any]:
    """Execute Azure SDK code with a 30 second timeout

    This tool allows executing arbitrary Azure SDK code to interact with Azure services.
    The code execution is sandboxed and has access to Azure management client libraries,
    json, and datetime modules. Pre-configured Azure clients are provided for common services.

    Available Azure clients in the execution namespace:
    - compute_client: Azure Compute Management Client (VMs, scale sets, etc.)
    - storage_client: Azure Storage Management Client (storage accounts, blobs, etc.)
    - resource_client: Azure Resource Management Client (resource groups, deployments)
    - network_client: Azure Network Management Client (VNets, NSGs, etc.)
    - monitor_client: Azure Monitor Management Client (metrics, alerts, etc.)
    - credential: The Azure credential object used for authentication
    - subscription_id: The Azure subscription ID being used

    You can provide Azure credentials directly through parameters:

    - azure_client_id: Azure client ID (service principal)
    - azure_client_secret: Azure client secret (service principal)
    - azure_tenant_id: Azure tenant ID
    - azure_subscription_id: Azure subscription ID

    If credentials are not provided, DefaultAzureCredential will be used, which supports:
    - Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
    - Azure CLI authentication (az login)
    - Managed Identity (when running on Azure)
    - Azure PowerShell
    - Interactive browser authentication (if enabled)

    Important:
        Break down complex tasks into smaller, manageable functions.
        Avoid writing large monolithic code blocks.
        Use appropriate Azure SDK patterns for resource management.
        Handle Azure-specific pagination and async operations properly.

    Note:
        The code execution is asynchronous, and it has a 30 second timeout.
        Azure SDK operations can be time-consuming, so structure your code efficiently.

    Example usage:
        # List all resource groups
        rg_list = resource_client.resource_groups.list()
        for rg in rg_list:
            print(f"Resource Group: {rg.name} in {rg.location}")

        # List VMs in a specific resource group
        vm_list = compute_client.virtual_machines.list("my-resource-group")
        for vm in vm_list:
            print(f"VM: {vm.name}, Status: {vm.provisioning_state}")

    Args:
        code (str): The Azure SDK code to execute
        azure_client_id (str, optional): Azure client ID
        azure_client_secret (str, optional): Azure client secret
        azure_tenant_id (str, optional): Azure tenant ID
        azure_subscription_id (str, optional): Azure subscription ID
        sanitize_python_code (callable, optional): Function to sanitize Python code

    Returns:
        Dict[str, Any]: Response containing:
            - success (bool): Whether execution succeeded
            - output (str): Captured stdout if successful
            - errors (str): Captured stderr if any
            - error (str): Error message if failed
            - error_type (str): Type of error if failed
            - traceback (str): Full traceback if failed

    Raises:
        TimeoutError: If code execution exceeds 30 seconds
    """
    try:
        # Get Azure credential and subscription ID
        credential, subscription_id = get_azure_credential(
            client_id=azure_client_id,
            client_secret=azure_client_secret,
            tenant_id=azure_tenant_id,
            subscription_id=azure_subscription_id,
        )

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
        if sanitize_python_code:
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