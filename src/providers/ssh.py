import os
import traceback
from datetime import datetime
from typing import Any, Dict

# SSH client library
import paramiko
from paramiko import AutoAddPolicy, ECDSAKey, Ed25519Key, RSAKey, SSHClient
from paramiko.ssh_exception import AuthenticationException, NoValidConnectionsError, SSHException


def get_ssh_client(
    hostname: str,
    username: str = "root",
    password: str = None,
    private_key: str = None,
    private_key_path: str = None,
    port: int = 22,
    timeout: int = 30,
    use_ssh_agent: bool = True,
) -> SSHClient:
    """
    Create an SSH client connection with secure credential handling.

    This function creates a secure SSH connection using temporal credentials.
    No credentials are persisted or stored permanently.

    Args:
        hostname (str): The hostname or IP address to connect to
        username (str, optional): SSH username (default: root)
        password (str, optional): SSH password for password authentication
        private_key (str, optional): Private key content as string
        private_key_path (str, optional): Path to private key file
        port (int, optional): SSH port (default: 22)
        timeout (int, optional): Connection timeout in seconds (default: 30)
        use_ssh_agent (bool, optional): Whether to use SSH agent for key auth (default: True)

    Returns:
        paramiko.SSHClient: Connected SSH client

    Raises:
        AuthenticationException: If authentication fails
        SSHException: If SSH connection fails
        ValueError: If insufficient authentication parameters provided
    """
    if not hostname:
        raise ValueError("Hostname is required for SSH connection")

    if not username:
        raise ValueError("Username is required for SSH connection")

    # Validate authentication parameters
    has_password = password is not None
    has_private_key = private_key is not None or private_key_path is not None

    if not has_password and not has_private_key and not use_ssh_agent:
        raise ValueError("At least one authentication method is required: password, private key, or SSH agent")

    print(f"Creating SSH connection to {username}@{hostname}:{port}")

    # Create SSH client with security settings
    client = SSHClient()

    # Security note: AutoAddPolicy automatically adds unknown hosts
    # In production, you might want to use a more restrictive policy
    client.set_missing_host_key_policy(AutoAddPolicy())

    try:
        # Prepare private key if provided
        pkey = None
        if private_key or private_key_path:
            pkey = _load_private_key(private_key, private_key_path)

        # Attempt connection with authentication
        client.connect(
            hostname=hostname,
            port=port,
            username=username,
            password=password,
            pkey=pkey,
            timeout=timeout,
            allow_agent=use_ssh_agent,
            look_for_keys=True,  # Look for keys in default locations
            compress=True,  # Enable compression for better performance
        )

        print(f"✅ SSH connection established to {hostname}")
        return client

    except AuthenticationException as e:
        print(f"❌ SSH authentication failed for {username}@{hostname}: {e}")
        client.close()
        raise
    except (SSHException, NoValidConnectionsError) as e:
        print(f"❌ SSH connection failed to {hostname}: {e}")
        client.close()
        raise
    except Exception as e:
        print(f"❌ Unexpected SSH error: {e}")
        client.close()
        raise


def _load_private_key(private_key_content: str = None, private_key_path: str = None) -> paramiko.PKey:
    """
    Load a private key from content string or file path.

    Supports RSA, Ed25519, and ECDSA key formats.
    Note: DSS/DSA keys are no longer supported due to security concerns.

    Args:
        private_key_content (str, optional): Private key as string
        private_key_path (str, optional): Path to private key file

    Returns:
        paramiko.PKey: Loaded private key object

    Raises:
        ValueError: If key cannot be loaded or is unsupported format
        FileNotFoundError: If key file doesn't exist
    """
    key_content = None

    if private_key_content:
        key_content = private_key_content
        print("Loading private key from provided content")
    elif private_key_path:
        if not os.path.exists(private_key_path):
            raise FileNotFoundError(f"Private key file not found: {private_key_path}")

        with open(private_key_path, "r") as key_file:
            key_content = key_file.read()
        print(f"Loading private key from file: {private_key_path}")
    else:
        raise ValueError("Either private_key_content or private_key_path must be provided")

    # Try different supported key types (RSA, Ed25519, ECDSA)
    # Note: DSS/DSA keys are no longer supported for security reasons
    key_classes = [RSAKey, Ed25519Key, ECDSAKey]

    # Check if this might be a DSS key and provide helpful error message
    if "BEGIN DSA PRIVATE KEY" in key_content or "ssh-dss" in key_content:
        raise ValueError(
            "DSS/DSA keys are no longer supported due to security concerns. "
            "Please use RSA (minimum 2048-bit), Ed25519, or ECDSA keys instead."
        )

    for key_class in key_classes:
        try:
            if private_key_content:
                # Load from string content
                from io import StringIO

                key_file_obj = StringIO(key_content)
                return key_class.from_private_key(key_file_obj)
            else:
                # Load from file path
                return key_class.from_private_key_file(private_key_path)
        except Exception:
            continue

    raise ValueError(
        "Unable to load private key - unsupported format or invalid key. "
        "Supported formats: RSA (minimum 2048-bit), Ed25519, ECDSA. "
        "DSS/DSA keys are no longer supported for security reasons."
    )


async def ssh_execute(
    hostname: str,
    command: str,
    username: str = "root",
    password: str = None,
    private_key: str = None,
    private_key_path: str = None,
    port: int = 22,
    timeout: int = 30,
    use_ssh_agent: bool = True,
    sanitize_command: bool = True,
) -> Dict[str, Any]:

    start_time = datetime.now()
    ssh_client = None

    try:
        # Basic command sanitization if enabled
        if sanitize_command:
            command = _sanitize_command(command)

        print(f"Executing SSH command on {hostname}: {command[:100]}...")

        # Establish SSH connection
        ssh_client = get_ssh_client(
            hostname=hostname,
            username=username,
            password=password,
            private_key=private_key,
            private_key_path=private_key_path,
            port=port,
            timeout=timeout,
            use_ssh_agent=use_ssh_agent,
        )

        # Execute command with timeout
        stdin, stdout, stderr = ssh_client.exec_command(command, timeout=timeout)

        # Wait for command completion with timeout
        exit_code = stdout.channel.recv_exit_status()

        # Read output and errors
        output = stdout.read().decode("utf-8", errors="replace")
        error_output = stderr.read().decode("utf-8", errors="replace")

        execution_time = (datetime.now() - start_time).total_seconds()

        # Close streams
        stdin.close()
        stdout.close()
        stderr.close()

        return {
            "success": True,
            "output": output,
            "error_output": error_output if error_output else None,
            "exit_code": exit_code,
            "execution_time": execution_time,
            "hostname": hostname,
            "command": command,
        }

    except AuthenticationException as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        return {
            "success": False,
            "error": f"SSH authentication failed: {str(e)}",
            "error_type": "AuthenticationException",
            "execution_time": execution_time,
            "hostname": hostname,
        }

    except SSHException as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        return {
            "success": False,
            "error": f"SSH connection error: {str(e)}",
            "error_type": "SSHException",
            "execution_time": execution_time,
            "hostname": hostname,
        }

    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "execution_time": execution_time,
            "hostname": hostname,
        }

    finally:
        # Always clean up SSH connection
        if ssh_client:
            try:
                ssh_client.close()
                print(f"SSH connection to {hostname} closed")
            except Exception as e:
                print(f"Warning: Error closing SSH connection: {e}")


def _sanitize_command(command: str) -> str:
    """
    Apply basic sanitization to SSH commands for security.

    This is a basic sanitization function that removes potentially dangerous
    command patterns. For production use, consider more comprehensive validation.

    Args:
        command (str): The command to sanitize

    Returns:
        str: Sanitized command

    Raises:
        ValueError: If command contains dangerous patterns
    """
    if not command or not command.strip():
        raise ValueError("Command cannot be empty")

    # Remove leading/trailing whitespace
    command = command.strip()

    # Basic checks for potentially dangerous patterns
    dangerous_patterns = [
        "rm -rf /",
        "mkfs",
        "dd if=",
        "format",
        ":(){ :|:& };:",  # Fork bomb
        "chmod 777",
        "chown root",
    ]

    command_lower = command.lower()
    for pattern in dangerous_patterns:
        if pattern in command_lower:
            raise ValueError(f"Command contains potentially dangerous pattern: {pattern}")

    return command
