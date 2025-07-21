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
import pulumi
import pulumi_aws as aws
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
    role = os.getenv("AWS_ROLE")
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION"),
    )
    if profile_name:
        print(f"Using profile: {profile_name}")
        session = boto3.Session(profile_name=profile_name)
    elif role:
        print(f"Assuming role: {role}")
        sts = session.client("sts")
        response = sts.assume_role(RoleArn=role, RoleSessionName="MiSesion", DurationSeconds=3600)
        session = boto3.Session(
            aws_access_key_id=response["Credentials"]["AccessKeyId"],
            aws_secret_access_key=response["Credentials"]["SecretAccessKey"],
            aws_session_token=response["Credentials"]["SessionToken"],
        )
    else:
        print("Creating session with default credentials")
    return session


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
        response = session.client("s3").list_buckets()/nprint("Session test: ", response)

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
        print(code)
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


# @mcp.tool
# async def pulumi_preview(code: str, stack_name: str, project_name: str) -> Dict[str, Any]:
#     """Preview Pulumi infrastructure changes without deploying them.

#     This tool allows you to see what changes would be made to your infrastructure
#     before actually deploying them. It's a safe way to validate your infrastructure
#     code changes.

#     Args:
#         code (str): The Pulumi program code to execute
#         stack_name (str): Name of the Pulumi stack to preview
#         project_name (str): Name of the Pulumi project

#     Returns:
#         Dict[str, Any]: Response containing:
#             - success (bool): Whether preview succeeded
#             - stack_name (str): Name of the stack previewed
#             - project_name (str): Name of the project
#             - changes (dict): Summary of resources to be added/updated/deleted
#             - code_executed (str): The sanitized code that was executed
#             - error (str): Error message if failed
#             - error_type (str): Type of error if failed
#             - traceback (str): Full traceback if failed

#     Raises:
#         TimeoutError: If preview execution exceeds configured timeout
#     """
#     try:
#         code = sanitize_python_code(code)

#         def program():
#             exec(code, {"pulumi": pulumi, "aws": aws, "pulumi_aws": aws})

#         # Create or select stack
#         stack = auto.create_or_select_stack(stack_name=stack_name, project_name=project_name, program=program)

#         # Run preview with timeout
#         preview_result = await asyncio.wait_for(
#             asyncio.get_event_loop().run_in_executor(None, lambda: stack.preview()),
#             timeout=120,
#         )

#         return {
#             "success": True,
#             "stack_name": stack_name,
#             "project_name": project_name,
#             "changes": preview_result.change_summary,
#             "code_executed": code,
#         }

#     except asyncio.TimeoutError:
#         return {
#             "success": False,
#             "error": "Pulumi preview timed out after 30 seconds",
#             "error_type": "TimeoutError",
#         }
#     except Exception as e:
#         return {
#             "success": False,
#             "error": str(e),
#             "error_type": type(e).__name__,
#             "traceback": traceback.format_exc(),
#         }


# @mcp.tool
# async def pulumi_up(code: str, stack_name: str, project_name: str) -> Dict[str, Any]:
#     """Deploy Pulumi infrastructure changes to your cloud environment.

#     This tool executes your Pulumi program and applies the infrastructure changes
#     to your cloud environment. It will create, update, or delete resources as
#     specified in your code.

#     Args:
#         code (str): The Pulumi program code to execute
#         stack_name (str): Name of the Pulumi stack to deploy
#         project_name (str): Name of the Pulumi project

#     Returns:
#         Dict[str, Any]: Response containing:
#             - success (bool): Whether deployment succeeded
#             - stack_name (str): Name of the stack deployed
#             - project_name (str): Name of the project
#             - summary (dict): Summary of resources added/updated/deleted
#             - code_executed (str): The sanitized code that was executed
#             - error (str): Error message if failed
#             - error_type (str): Type of error if failed
#             - traceback (str): Full traceback if failed

#     Raises:
#         TimeoutError: If deployment execution exceeds configured timeout
#     """
#     try:
#         code = sanitize_python_code(code)

#         def program():
#             exec(code, {"pulumi": pulumi, "aws": aws, "pulumi_aws": aws})

#         # Create or select stack
#         stack = auto.create_or_select_stack(stack_name=stack_name, project_name=project_name, program=program)

#         # Run deployment with timeout
#         up_result = await asyncio.wait_for(
#             asyncio.get_event_loop().run_in_executor(None, lambda: stack.up()),
#             timeout=120,
#         )

#         return {
#             "success": True,
#             "stack_name": stack_name,
#             "project_name": project_name,
#             "outputs": up_result.outputs,
#             "summary": up_result.summary,
#             "code_executed": code,
#         }

#     except asyncio.TimeoutError:
#         return {
#             "success": False,
#             "error": "Pulumi deployment timed out after 120 seconds",
#             "error_type": "TimeoutError",
#         }
#     except Exception as e:
#         return {
#             "success": False,
#             "error": str(e),
#             "error_type": type(e).__name__,
#             "traceback": traceback.format_exc(),
#         }


if __name__ == "__main__":
    session = get_aws_session()
    # Test session aws with a simple command to list buckets s3
    response = session.client("s3").list_buckets()
    print("Session test: ", response)
    mcp.run(transport="sse", host="0.0.0.0", port=8080, path="/mcp")
