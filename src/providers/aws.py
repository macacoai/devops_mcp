import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict

import boto3
from fastmcp import FastMCP


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


async def boto3_execute(
        code: str,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        aws_session_token: str = None,
        aws_region: str = None,
        aws_profile: str = None,
        aws_role_arn: str = None,
        sanitize_python_code=None,
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
        if sanitize_python_code:
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