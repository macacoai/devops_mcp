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

# Import cloud providers
from providers.aws import get_aws_session, boto3_execute
from providers.azure import get_azure_credential, get_azure_clients, azure_execute
from azure.mgmt.resource import ResourceManagementClient

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


# Register the modified tool functions with FastMCP
@mcp.tool
async def boto3_execute_wrapper(
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
    """
    return await boto3_execute(
        code=code,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_session_token=aws_session_token,
        aws_region=aws_region,
        aws_profile=aws_profile,
        aws_role_arn=aws_role_arn,
        sanitize_python_code=sanitize_python_code,
    )


@mcp.tool
async def azure_execute_wrapper(
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
    """
    return await azure_execute(
        code=code,
        azure_client_id=azure_client_id,
        azure_client_secret=azure_client_secret,
        azure_tenant_id=azure_tenant_id,
        azure_subscription_id=azure_subscription_id,
        sanitize_python_code=sanitize_python_code,
    )


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
    print("🔧 Available tools: boto3_execute_wrapper, azure_execute_wrapper")

    # Start the MCP server
    mcp.run(transport="sse", host="0.0.0.0", port=8080, path="/mcp")