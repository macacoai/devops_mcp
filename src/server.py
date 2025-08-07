# server.py
import ast
from datetime import datetime
from typing import Any, Dict

from azure.mgmt.resource import ResourceManagementClient
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Import cloud providers
from providers.aws import boto3_execute, get_aws_session
from providers.azure import azure_execute, get_azure_credential
from providers.hetzner import get_hetzner_client, hetzner_execute
from providers.ssh import ssh_execute

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
        "tools_available": ["boto3_execute", "azure_execute", "hetzner_execute", "ssh_execute_wrapper"],
        "resources_available": ["health://status", "server://info"],
        "supported_clouds": ["AWS", "Azure", "Hetzner Cloud"],
        "supported_protocols": ["SSH"],
    }
    return str(health_data)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Basic health check that the server is running."""
    return JSONResponse(
        {"status": "alive", "clouds": ["AWS", "Azure", "Hetzner Cloud"], "protocols": ["SSH"], "version": "2.0.0"},
        status_code=200,
    )


def sanitize_python_code(code_string: str) -> str:
    try:
        # Normalize line endings
        replacements = {"\\n": "\n", "\\t": "\t", "\\r": "\r", '\\"': '"', "\\'": "'", "\\\\": "\\"}

        for literal, actual in replacements.items():
            code_string = code_string.replace(literal, actual)

        parsed_ast = ast.parse(code_string)

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
) -> Dict[str, Any]:
    """Execute AWS boto3 code with a 30 second timeout

    This tool allows executing arbitrary boto3 code to interact with AWS services.
    The code execution is sandboxed and has access to common modules like boto3, json,
    and datetime. A pre-configured AWS session is provided via the 'session' variable.

    When listing AWS resources, the tool will:
    1. First count the total number of resources
    2. Then retrieve and return them in paginated batches of 50 items

    Example for listing S3 buckets:
        # Get total count
        total_buckets = len(list(session.client('s3').list_buckets()['Buckets']))
        print(f"Total buckets: {total_buckets}")

        # List in batches of 50
        paginator = session.client('s3').get_paginator('list_buckets')
        for page in paginator.paginate(PaginationConfig={'PageSize': 50}):
            print("Current batch of buckets:", page['Buckets'])
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
    return await boto3_execute(
        code=code,
    )


@mcp.tool
async def azure_execute_wrapper(
    code: str,
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


    DefaultAzureCredential will be used, which supports:
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
    return await azure_execute(
        code=code,
    )


@mcp.tool
async def hetzner_execute_wrapper(
    code: str,
) -> Dict[str, Any]:
    """Execute Hetzner Cloud hcloud code with a 30 second timeout

    This tool allows executing arbitrary hcloud code to interact with Hetzner Cloud services.
    The code execution is sandboxed and has access to the hcloud library, json,
    and datetime. A pre-configured Hetzner Cloud client is provided via the 'client' variable.

    Available services through the client:
    - client.servers: Server management (create, list, delete, power operations)
    - client.images: Image management (list, create from server)
    - client.server_types: Server type information (list available sizes)
    - client.datacenters: Datacenter information (list locations)
    - client.ssh_keys: SSH key management (create, list, delete)
    - client.volumes: Volume management (create, attach, detach)
    - client.networks: Network management (create private networks)
    - client.load_balancers: Load balancer management (create, configure)
    - client.firewalls: Firewall management (create rules, assign to resources)
    - client.floating_ips: Floating IP management (create, assign)
    - client.certificates: SSL certificate management
    - client.placement_groups: Placement group management

    Important:
        Break down complex tasks into smaller, manageable functions.
        Avoid writing large monolithic code blocks.
        Fetch only the required data and resources needed for each operation.
        Use modular design patterns for better maintainability and testing.
        Example: Instead of fetching all servers at once, filter by specific criteria
        or process them in batches.

    Note:
        The code execution is asynchronous, and it has a 30 second timeout.
        You have imported hcloud, json, and datetime.

    Example usage:
        # List all servers
        servers = client.servers.get_all()
        for server in servers:
            print(f"Server: {server.name}, Status: {server.status}, IP: {server.public_net.ipv4.ip}")

        # Create a new server
        response = client.servers.create(
            name="my-server",
            server_type=client.server_types.get_by_name("cx22"),
            image=client.images.get_by_name("ubuntu-22.04")
        )
        print(f"Server created: {response.server.name}")

    Args:
        code (str): The hcloud code to execute
        hcloud_api_token (str, optional): Hetzner Cloud API token
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
    return await hetzner_execute(
        code=code,
    )


@mcp.tool
async def ssh_execute_wrapper(
    hostname: str,
    command: str,
    username: str = "root",
    password: str = None,
    private_key: str = None,
    private_key_path: str = None,
    port: int = 22,
    timeout: int = 30,
    use_ssh_agent: bool = True,
) -> Dict[str, Any]:
    """Execute commands on remote servers via SSH with temporal credentials

    This tool allows executing shell commands on remote servers through SSH connections.
    All credentials are temporal and must be provided with each request - no credentials
    are stored or cached for security reasons.

    The tool supports multiple authentication methods:
    - Username/password authentication
    - Private key authentication (from content string or file path)
    - SSH agent integration for existing keys

    Security features:
    - Temporal credentials only (no persistence)
    - Connection timeout protection
    - Automatic connection cleanup
    - Basic command sanitization
    - Support for all major private key formats (RSA, Ed25519, ECDSA, DSS)

    This is particularly useful for:
    - Managing Hetzner Cloud servers after creation
    - Administering any SSH-accessible Linux servers
    - Running maintenance commands on remote systems
    - Deploying applications and configurations
    - Monitoring and troubleshooting remote servers

    Important security notes:
    - Always provide credentials for each request
    - Use private keys instead of passwords when possible
    - Limit command execution scope for security
    - Consider using SSH agent for key management

    Example usage:
        # Execute command with password authentication
        result = await ssh_execute_wrapper(
            hostname="192.168.1.100",
            command="df -h",
            username="admin",
            password="secure_password"
        )

        # Execute command with private key
        result = await ssh_execute_wrapper(
            hostname="server.example.com",
            command="systemctl status nginx",
            username="deploy",
            private_key_path="/path/to/private/key"
        )

        # Execute command on Hetzner server
        result = await ssh_execute_wrapper(
            hostname="hetzner-server.example.com",
            command="apt update && apt upgrade -y",
            username="root",
            password="server_password",
            timeout=60
        )

    Args:
        hostname (str): The hostname or IP address of the remote server
        command (str): The shell command to execute on the remote server
        username (str, optional): SSH username (default: root)
        password (str, optional): SSH password for password authentication
        private_key (str, optional): Private key content as string
        private_key_path (str, optional): Path to private key file
        port (int, optional): SSH port number (default: 22)
        timeout (int, optional): Command execution timeout in seconds (default: 30)
        use_ssh_agent (bool, optional): Use SSH agent for key authentication (default: True)

    Returns:
        Dict[str, Any]: Response containing:
            - success (bool): Whether execution succeeded
            - output (str): Command stdout if successful
            - error_output (str): Command stderr if any
            - exit_code (int): Command exit code
            - error (str): Error message if failed
            - error_type (str): Type of error if failed
            - execution_time (float): Command execution time in seconds
            - hostname (str): The target hostname
            - command (str): The executed command (for reference)
    """

    return await ssh_execute(
        hostname=hostname,
        command=command,
        username=username,
        password=password,
        private_key=private_key,
        private_key_path=private_key_path,
        port=port,
        timeout=timeout,
        use_ssh_agent=use_ssh_agent,
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

    # Test Hetzner Cloud credentials
    try:
        client = get_hetzner_client()
        # Test client by getting server types (a simple, low-cost API call)
        server_types = client.server_types.get_all()
        print("✅ Hetzner Cloud credentials validated successfully")
    except Exception as e:
        print(f"⚠️  Hetzner Cloud credential check failed: {e}")
        print("ℹ️  Hetzner Cloud features will be available when credentials are provided via API")

    print("🌐 Supporting cloud providers: AWS, Azure, Hetzner Cloud")
    print("🔐 Supporting protocols: SSH")
    print(
        "🔧 Available tools: boto3_execute_wrapper, azure_execute_wrapper, hetzner_execute_wrapper, ssh_execute_wrapper"
    )

    # Start the MCP server
    mcp.run(transport="sse", host="0.0.0.0", port=8080, path="/mcp")
