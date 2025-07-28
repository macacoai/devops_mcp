# server.py
import ast
import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict

import black
import boto3
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Azure imports
from azure.identity import DefaultAzureCredential, ClientSecretCredential, AzureCliCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient

mcp = FastMCP("Multi-Cloud DevOps 🚀")


@mcp.resource("health://status")
def health_status() -> str:
    """Get the current health status of the server"""
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server_name": "multi-cloud-devops",
        "version": "2.0.0",
        "uptime": "running",
        "tools_available": [
            "boto3_execute",
            "azure_execute",
            "add", "subtract", "multiply", "divide"
        ],
        "resources_available": ["health://status", "server://info"],
        "supported_clouds": ["AWS", "Azure"],
    }
    return str(health_data)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Basic health check that the server is running."""
    return JSONResponse({
        "status": "alive",
        "clouds": ["AWS", "Azure"],
        "version": "2.0.0"
    }, status_code=200)


def get_aws_session(access_key_id=None, secret_access_key=None, session_token=None, region_name=None, profile_name=None,
                    role_arn=None):
    """
    Get an AWS session with credentials from parameters or environment variables.

    Parameters take precedence over environment variables.

    Args:
        access_key_id (str, optional): AWS access key ID
        secret_access_key (str, optional): AWS secret access key
        session_token (str, optional): AWS session token
        region_name (str, optional): AWS region name
        profile_name (str, optional): AWS profile name
        role_arn (str, optional): AWS IAM role ARN to assume

    Returns:
        boto3.Session: Configured AWS session
    """
    # Use parameters if provided, otherwise fall back to environment variables
    env_profile_name = os.getenv("AWS_PROFILE")
    env_role_arn = os.getenv("AWS_ROLE")

    # Parameter values take precedence over environment variables
    profile_name = profile_name or env_profile_name
    role_arn = role_arn or env_role_arn

    # Create initial session with either provided credentials or environment variables
    session = boto3.Session(
        aws_access_key_id=access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=session_token,
        region_name=region_name or os.getenv("AWS_DEFAULT_REGION"),
    )

    # Use profile if specified
    if profile_name:
        print(f"Using AWS profile: {profile_name}")
        session = boto3.Session(profile_name=profile_name)
    # Use role if specified
    elif role_arn:
        print(f"Assuming AWS role: {role_arn}")
        sts = session.client("sts")
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="MiSesion",
            DurationSeconds=3600
        )
        session = boto3.Session(
            aws_access_key_id=response["Credentials"]["AccessKeyId"],
            aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
            aws_session_token=response["Credentials"]["SessionToken"],
        )
    else:
        # Log the credential source we're using
        if access_key_id:
            print("Creating AWS session with provided credentials")
        else:
            print("Creating AWS session with default credentials")

    return session


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


def sanitize_python_code(code_string: str) -> str:
    try:
        # Normalize line endings
        replacements = {"\\n": "\n", "\\t": "\t", "\\r": "\r", '\\"': '"', "\\'": "'", "\\\\": "\\"}

        for literal, actual in replacements.items():
            code_string = code_string.replace(literal, actual)

        # Format with black
        formatted = black.format_str(code_string, mode=black.FileMode())

        parsed_ast = ast.parse(formatted)

        # Iterate through the nodes and check for potentially unsafe constructs
        for node in ast.walk(parsed_ast):
            # Example: Disallow function calls to specific potentially dangerous functions
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ["eval", "exec", "open", "subprocess.call"]:
                    raise ValueError(f"Calling '{node.func.id}' is not allowed.")

        # If no unsafe constructs are found, the code is considered sanitized
        return code_string

    except SyntaxError as e:
        raise ValueError(f"Invalid Python syntax: {e}")
    except ValueError as e:
        raise ValueError(f"Sanitization failed: {e}")


@mcp.tool
async def boto3_execute(
        code: str,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        aws_session_token: str = None,
        aws_region: str = None,
        aws_profile: str = None,
        aws_role_arn: str = None,
) -> Dict[str, Any]:
    """Execute AWS boto3 code with a 30 second timeout

    This tool allows executing arbitrary boto3 code to interact with AWS services.
    The code execution is sandboxed and has access to common modules like boto3, json,
    and datetime. A pre-configured AWS session is provided via the 'session' variable.

    You can provide AWS credentials directly through parameters:

    - aws_access_key_id: AWS access key ID
    - aws_secret_access_key: AWS secret access key
    - aws_session_token: AWS session token (optional)
    - aws_region: AWS region name
    - aws_profile: AWS profile name (optional)
    - aws_role_arn: AWS IAM role ARN to assume (optional)

    If credentials are not provided, they will be retrieved from environment variables.

    Important:
        Break down complex tasks into smaller, manageable functions.
        Avoid writing large monolithic code blocks.
        Fetch only the required data and resources needed for each operation.
        Use modular design patterns for better maintainability and testing.
        Example: Instead of fetching all S3 buckets at once, get them in batches
        or filter by specific criteria.
    Note:
        The code execution is asynchronous, and it has a 30 second timeout.
        You have imported boto3, json, and datetime.

    Example usage:
        response = session.client("s3").list_buckets()
        print("Session test: ", response)

    Args:
        code (str): The boto3 code to execute
        aws_access_key_id (str, optional): AWS access key ID
        aws_secret_access_key (str, optional): AWS secret access key
        aws_session_token (str, optional): AWS session token
        aws_region (str, optional): AWS region name
        aws_profile (str, optional): AWS profile name
        aws_role_arn (str, optional): AWS IAM role ARN to assume

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
    # Check if AWS credentials were provided directly
    if aws_access_key_id and not aws_secret_access_key:
        return {
            "success": False,
            "error": "aws_secret_access_key is required when aws_access_key_id is provided",
            "error_type": "ValueError",
        }

    # Build execution namespace based on context
    namespace = {
        "boto3": boto3,
        "json": json,
        "datetime": datetime,
        "timedelta": timedelta,
        "session": get_aws_session(
            access_key_id=aws_access_key_id,
            secret_access_key=aws_secret_access_key,
            session_token=aws_session_token,
            region_name=aws_region,
            profile_name=aws_profile,
            role_arn=aws_role_arn,
        ),
    }

    try:
        # Use asyncio.wait_for for timeout
        output_capture = StringIO()
        error_capture = StringIO()
        code = sanitize_python_code(code)
        print(f"Executing AWS code: {code[:100]}...")
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


@mcp.tool
async def azure_execute(
        code: str,
        azure_client_id: str = None,
        azure_client_secret: str = None,
        azure_tenant_id: str = None,
        azure_subscription_id: str = None,
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


if __name__ == "__main__":
    print("🚀 Starting Multi-Cloud DevOps MCP Server...")

    # Test AWS credentials
    try:
        session = get_aws_session()
        response = session.client("s3").list_buckets()
        print("✅ AWS credentials validated successfully")
    except Exception as e:
        print(f"⚠️  AWS credential check failed: {e}")
        print("ℹ️  AWS features will be available when credentials are provided via API")

    # Test Azure credentials
    try:
        credential, subscription_id = get_azure_credential()
        # Test credential by creating a simple client
        resource_client = ResourceManagementClient(credential, subscription_id)
        print("✅ Azure credentials validated successfully")
    except Exception as e:
        print(f"⚠️  Azure credential check failed: {e}")
        print("ℹ️  Azure features will be available when credentials are provided via API")

    print("🌐 Supporting cloud providers: AWS, Azure")
    print("🔧 Available tools: boto3_execute, azure_execute")

    # Start the MCP server
    mcp.run(transport="sse", host="0.0.0.0", port=8080, path="/mcp")