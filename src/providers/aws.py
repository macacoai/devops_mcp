import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict

import boto3

from server import sanitize_python_code


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
    if role:
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


async def boto3_execute(
    code: str,
) -> Dict[str, Any]:
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
                timeout=None,
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
