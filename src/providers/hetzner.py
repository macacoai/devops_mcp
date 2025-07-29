import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict

# Hetzner Cloud imports
from hcloud import Client
from hcloud.actions import BoundAction
from hcloud.certificates import BoundCertificate
from hcloud.datacenters import BoundDatacenter
from hcloud.firewalls import BoundFirewall
from hcloud.floating_ips import BoundFloatingIP
from hcloud.images import BoundImage
from hcloud.load_balancers import BoundLoadBalancer
from hcloud.networks import BoundNetwork
from hcloud.placement_groups import BoundPlacementGroup
from hcloud.server_types import BoundServerType
from hcloud.servers import BoundServer
from hcloud.ssh_keys import BoundSSHKey
from hcloud.volumes import BoundVolume


def get_hetzner_client(hcloud_api_token=None):
    """
    Get a Hetzner Cloud client with API token from parameters or environment variables.

    Parameters take precedence over environment variables.

    Args:
        hcloud_api_token (str, optional): Hetzner Cloud API token

    Returns:
        hcloud.Client: Configured Hetzner Cloud client
    """
    # Use parameter if provided, otherwise fall back to environment variable
    api_token = hcloud_api_token or os.getenv("HCLOUD_API_TOKEN")

    if not api_token:
        raise ValueError(
            "Hetzner Cloud API token is required. Set HCLOUD_API_TOKEN environment variable or provide hcloud_api_token parameter."
        )

    # Log the credential source we're using
    if hcloud_api_token:
        print("Creating Hetzner Cloud client with provided API token")
    else:
        print("Creating Hetzner Cloud client with environment variable token")

    return Client(token=api_token)


async def hetzner_execute(
        code: str,
        hcloud_api_token: str = None,
        sanitize_python_code=None,
) -> Dict[str, Any]:
    """Execute Hetzner Cloud hcloud code with a 30 second timeout

    This tool allows executing arbitrary hcloud code to interact with Hetzner Cloud services.
    The code execution is sandboxed and has access to the hcloud library, json,
    and datetime. A pre-configured Hetzner Cloud client is provided via the 'client' variable.

    You can provide Hetzner Cloud credentials directly through parameters:

    - hcloud_api_token: Hetzner Cloud API token

    If credentials are not provided, they will be retrieved from environment variables.

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
    try:
        # Get Hetzner Cloud client
        client = get_hetzner_client(hcloud_api_token=hcloud_api_token)

        # Build execution namespace
        namespace = {
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
            "client": client,
            # Provide direct access to hcloud classes for advanced usage
            "Client": Client,
            "BoundAction": BoundAction,
            "BoundCertificate": BoundCertificate,
            "BoundDatacenter": BoundDatacenter,
            "BoundFirewall": BoundFirewall,
            "BoundFloatingIP": BoundFloatingIP,
            "BoundImage": BoundImage,
            "BoundLoadBalancer": BoundLoadBalancer,
            "BoundNetwork": BoundNetwork,
            "BoundPlacementGroup": BoundPlacementGroup,
            "BoundServerType": BoundServerType,
            "BoundServer": BoundServer,
            "BoundSSHKey": BoundSSHKey,
            "BoundVolume": BoundVolume,
        }

        # Use asyncio.wait_for for timeout
        output_capture = StringIO()
        error_capture = StringIO()
        if sanitize_python_code:
            code = sanitize_python_code(code)
        print(f"Executing Hetzner Cloud code: {code[:100]}...")

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