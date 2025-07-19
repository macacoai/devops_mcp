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
from pulumi import automation as auto
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP("Devops AWS 🚀")


@mcp.resource("health://status")
def health_status() -> str:
    """Get the current health status of the server"""
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server_name": "dev-ops-aws",
        "version": "1.0.0",
        "uptime": "running",
        "tools_available": ["add", "subtract", "multiply", "divide"],
        "resources_available": ["health://status", "server://info"],
    }
    return str(health_data)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Basic health check that the server is running."""
    return JSONResponse({"status": "alive"}, status_code=200)


def get_aws_session():
    profile_name = os.getenv("AWS_PROFILE")
    if profile_name:
        return boto3.Session(profile_name=profile_name)
    else:
        return boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("AWS_DEFAULT_REGION"),
        )


def sanitize_python_code(code_string: str) -> str:
    try:
        # Normalize line endings
        replacements = {"\\n": "\n", "\\t": "\t", "\\r": "\r", '\\"': '"', "\\'": "'", "\\\\": "\\"}

        for literal, actual in replacements.items():
            code_string = code_string.replace(literal, actual)

        # Formatea con black
        formatted = black.format_str(code_string, mode=black.FileMode())

        parsed_ast = ast.parse(formatted)

        # Iterate through the nodes and check for potentially unsafe constructs
        for node in ast.walk(parsed_ast):
            # Example: Disallow import statements (to prevent importing malicious modules)
            # if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            #     raise ValueError("Import statements are not allowed.")

            # Example: Disallow function calls to specific potentially dangerous functions (e.g., 'eval', 'exec')
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ["eval", "exec", "open", "subprocess.call"]:
                    raise ValueError(f"Calling '{node.func.id}' is not allowed.")

            # Add more checks based on your security requirements
            # e.g., disallow file system operations, network access, etc.

        # If no unsafe constructs are found, the code is considered sanitized
        return code_string

    except SyntaxError as e:
        raise ValueError(f"Invalid Python syntax: {e}")
    except ValueError as e:
        raise ValueError(f"Sanitization failed: {e}")


@mcp.tool
async def boto3_execute(code: str) -> Dict[str, Any]:
    """Execute AWS boto3 code with a 30 second timeout

    This tool allows executing arbitrary boto3 code to interact with AWS services.
    The code execution is sandboxed and has access to common modules like boto3, json,
    and datetime. A pre-configured AWS session is provided via the 'session' variable.

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
    # Build execution namespace based on context
    namespace = {
        "boto3": boto3,
        "json": json,
        "datetime": datetime,
        "timedelta": timedelta,
        "session": get_aws_session(),
    }

    try:
        # Use asyncio.wait_for for timeout
        output_capture = StringIO()
        error_capture = StringIO()
        code = sanitize_python_code(code)
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


async def pulumi_preview(self, code: str, stack_name: str, project_name: str) -> Dict[str, Any]:
    """Preview Pulumi infrastructure changes"""
    try:

        def program():
            exec(code, {"pulumi": pulumi, "aws": aws, "pulumi_aws": aws})

        # Create or select stack
        stack = auto.create_or_select_stack(stack_name=stack_name, project_name=project_name, program=program)

        # Run preview with timeout
        preview_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, lambda: stack.preview()),
            timeout=self.config.execution_timeout,
        )

        return {
            "success": True,
            "stack_name": stack_name,
            "project_name": project_name,
            "changes": preview_result.change_summary,
            "code_executed": code,
        }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Pulumi preview timed out after " f"{self.config.execution_timeout} seconds",
            "error_type": "TimeoutError",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
        }


async def _pulumi_up(self, code: str, stack_name: str, project_name: str) -> Dict[str, Any]:
    """Deploy Pulumi infrastructure"""
    try:

        def program():
            exec(code, {"pulumi": pulumi, "aws": aws, "pulumi_aws": aws})

        # Create or select stack
        stack = auto.create_or_select_stack(stack_name=stack_name, project_name=project_name, program=program)

        # Run deployment with timeout
        up_result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, lambda: stack.up()),
            timeout=self.config.execution_timeout,
        )

        return {
            "success": True,
            "stack_name": stack_name,
            "project_name": project_name,
            "outputs": up_result.outputs,
            "summary": up_result.summary,
            "code_executed": code,
        }

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Pulumi deployment timed out after " f"{self.config.execution_timeout} seconds",
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
    mcp.run(transport="sse", host="0.0.0.0", port=8080)
