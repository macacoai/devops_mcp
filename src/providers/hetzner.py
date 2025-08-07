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

from server import sanitize_python_code


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
        raise ValueError("Hetzner Cloud API token is required. Set HCLOUD_API_TOKEN environment variable.")

    # Log the credential source we're using
    if hcloud_api_token:
        print("Creating Hetzner Cloud client with provided API token")
    else:
        print("Creating Hetzner Cloud client with environment variable token")

    return Client(token=api_token)


async def hetzner_execute(
    code: str,
) -> Dict[str, Any]:
    try:
        # Get Hetzner Cloud client
        client = get_hetzner_client(hcloud_api_token=os.getenv("HCLOUD_API_TOKEN"))

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
