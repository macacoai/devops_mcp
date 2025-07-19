"""
AWS DevOps MCP Server
Provides low-level tools for boto3, pulumi operations and function management
"""

import argparse
import asyncio
import json
import os
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List

import boto3
import pulumi
import pulumi_aws as aws
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from pulumi import automation as auto

from helpers import AWSHelpers, CostUtils, MonitoringUtils
from pulumi_backend_manager import PulumiBackendManager
from storage import FunctionStorage


def parse_arguments():
    """Parse command-line arguments with environment variable fallbacks"""
    parser = argparse.ArgumentParser(
        description="AWS DevOps MCP Server - " "Provides low-level tools for AWS operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --region us-west-2 --profile production
  %(prog)s --max-functions 50 --debug
  %(prog)s --database-path /tmp/functions.db --aws-region eu-west-1

Environment Variables:
  All arguments can also be set via environment variables:
  AWS_DEFAULT_REGION, AWS_PROFILE, DATABASE_PATH, MAX_FUNCTIONS, etc.
        """,
    )

    # AWS Configuration
    aws_group = parser.add_argument_group("AWS Configuration")
    aws_group.add_argument(
        "--aws-region",
        "--region",
        default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        help="AWS region (default: %(default)s, env: AWS_DEFAULT_REGION)",
    )
    aws_group.add_argument(
        "--aws-profile",
        "--profile",
        default=os.getenv("AWS_PROFILE"),
        help="AWS CLI profile to use (env: AWS_PROFILE)",
    )
    aws_group.add_argument(
        "--aws-access-key-id",
        default=os.getenv("AWS_ACCESS_KEY_ID"),
        help="AWS Access Key ID (env: AWS_ACCESS_KEY_ID)",
    )
    aws_group.add_argument(
        "--aws-secret-access-key",
        default=os.getenv("AWS_SECRET_ACCESS_KEY"),
        help="AWS Secret Access Key (env: AWS_SECRET_ACCESS_KEY)",
    )

    # Pulumi Configuration
    pulumi_group = parser.add_argument_group("Pulumi Configuration")
    pulumi_group.add_argument(
        "--pulumi-token",
        default=os.getenv("PULUMI_ACCESS_TOKEN"),
        help="Pulumi access token (env: PULUMI_ACCESS_TOKEN)",
    )
    pulumi_group.add_argument(
        "--pulumi-backend-url",
        default=os.getenv("PULUMI_BACKEND_URL"),
        help="Pulumi backend URL (env: PULUMI_BACKEND_URL)",
    )
    pulumi_group.add_argument(
        "--auto-create-pulumi-backend",
        action="store_true",
        default=os.getenv("AUTO_CREATE_PULUMI_BACKEND", "true").lower() in ("true", "1", "yes", "on"),
        help="Auto-create Pulumi backend if it doesn't exist "
        "(default: %(default)s, env: AUTO_CREATE_PULUMI_BACKEND)",
    )

    # Server Configuration
    server_group = parser.add_argument_group("Server Configuration")
    server_group.add_argument(
        "--database-path",
        "--db-path",
        default=os.getenv("DATABASE_PATH", "data/functions.db"),
        help="Path to function storage database " "(default: %(default)s, env: DATABASE_PATH)",
    )
    server_group.add_argument(
        "--max-functions",
        type=int,
        default=int(os.getenv("MAX_FUNCTIONS", "20")),
        help="Maximum number of functions to store " "(default: %(default)s, env: MAX_FUNCTIONS)",
    )
    server_group.add_argument(
        "--debug",
        action="store_true",
        default=os.getenv("DEBUG", "false").lower() in ("true", "1", "yes", "on"),
        help="Enable debug mode (env: DEBUG)",
    )
    server_group.add_argument(
        "--execution-timeout",
        type=int,
        default=int(os.getenv("EXECUTION_TIMEOUT", "300")),
        help="Code execution timeout in seconds " "(default: %(default)s, env: EXECUTION_TIMEOUT)",
    )

    # Security Configuration
    security_group = parser.add_argument_group("Security Configuration")
    security_group.add_argument(
        "--enable-pulumi",
        action="store_true",
        default=os.getenv("ENABLE_PULUMI_OPERATIONS", "true").lower() in ("true", "1", "yes", "on"),
        help="Enable Pulumi operations " "(default: %(default)s, env: ENABLE_PULUMI_OPERATIONS)",
    )
    security_group.add_argument(
        "--enable-function-storage",
        action="store_true",
        default=os.getenv("ENABLE_FUNCTION_STORAGE", "true").lower() in ("true", "1", "yes", "on"),
        help="Enable function storage " "(default: %(default)s, env: ENABLE_FUNCTION_STORAGE)",
    )
    security_group.add_argument(
        "--enable-boto3-execution",
        action="store_true",
        default=os.getenv("ENABLE_BOTO3_EXECUTION", "true").lower() in ("true", "1", "yes", "on"),
        help="Enable boto3 code execution " "(default: %(default)s, env: ENABLE_BOTO3_EXECUTION)",
    )

    # Cost Analysis Configuration
    cost_group = parser.add_argument_group("Cost Analysis Configuration")
    cost_group.add_argument(
        "--cost-analysis-days",
        type=int,
        default=int(os.getenv("COST_ANALYSIS_DEFAULT_DAYS", "30")),
        help="Default cost analysis period in days " "(default: %(default)s, env: COST_ANALYSIS_DEFAULT_DAYS)",
    )
    cost_group.add_argument(
        "--cost-alert-threshold",
        type=float,
        default=float(os.getenv("COST_ALERT_THRESHOLD", "100.0")),
        help="Cost threshold for alerts in USD " "(default: %(default)s, env: COST_ALERT_THRESHOLD)",
    )

    return parser.parse_args()


class AWSDevOpsMCPServer:
    """MCP Server for AWS DevOps operations"""

    def __init__(self, config=None):
        self.config = config or parse_arguments()

        # Print configuration if debug mode is enabled
        if self.config.debug:
            print("🐛 Debug mode enabled")
            print(f"📍 AWS Region: {self.config.aws_region}")
            print(f"👤 AWS Profile: {self.config.aws_profile or 'default'}")
            print(f"💾 Database Path: {self.config.database_path}")
            print(f"📊 Max Functions: {self.config.max_functions}")

        # Setup AWS session with configuration
        session_kwargs = {}
        if self.config.aws_profile:
            session_kwargs["profile_name"] = self.config.aws_profile
        if self.config.aws_region:
            session_kwargs["region_name"] = self.config.aws_region

        # Set AWS credentials if provided via arguments
        if self.config.aws_access_key_id and self.config.aws_secret_access_key:
            session_kwargs.update(
                {
                    "aws_access_key_id": self.config.aws_access_key_id,
                    "aws_secret_access_key": self.config.aws_secret_access_key,
                }
            )

        self.aws_session = boto3.Session(**session_kwargs)

        # Set Pulumi environment variables if provided
        if self.config.pulumi_token:
            os.environ["PULUMI_ACCESS_TOKEN"] = self.config.pulumi_token

        # Setup Pulumi backend with auto-creation if enabled
        if self.config.pulumi_backend_url:
            backend_manager = PulumiBackendManager(aws_session=self.aws_session, debug=self.config.debug)

            backend_result = backend_manager.setup_backend(
                self.config.pulumi_backend_url, auto_create=self.config.auto_create_pulumi_backend
            )

            if backend_result["success"]:
                os.environ["PULUMI_BACKEND_URL"] = self.config.pulumi_backend_url
                if self.config.debug:
                    print(f"🔧 Pulumi Backend: {backend_result['message']}")
                    if backend_result.get("created"):
                        print(f"✨ Backend created: " f"{backend_result.get('backend_type')}")
            else:
                error_msg = "❌ Pulumi backend setup failed: " f"{backend_result['error']}"
                if self.config.debug:
                    print(error_msg)
                    if "suggestion" in backend_result:
                        print(f"💡 Suggestion: " f"{backend_result['suggestion']}")
                # Continue without failing, but warn user
                print(f"⚠️ Warning: {error_msg}")

        # Initialize server components
        self.server = Server("aws-devops-mcp")
        self.storage = FunctionStorage(self.config.database_path, max_functions=self.config.max_functions)
        self.aws_helpers = AWSHelpers(session=self.aws_session)
        self.cost_utils = CostUtils()
        self.monitoring_utils = MonitoringUtils()
        self._setup_tools()

    def _setup_tools(self):
        """Setup MCP tools based on configuration"""

        @self.server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            tools = []

            # Always include boto3_execute if enabled
            if self.config.enable_boto3_execution:
                tools.append(
                    Tool(
                        name="boto3_execute",
                        description="Execute arbitrary boto3 Python code",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "code": {"type": "string", "description": "Python code using boto3"},
                                "context": {
                                    "type": "string",
                                    "enum": ["general", "finops", "devops", "security"],
                                    "description": "Execution context for smart " "imports",
                                    "default": "general",
                                },
                            },
                            "required": ["code"],
                        },
                    )
                )

            # Include Pulumi tools if enabled
            if self.config.enable_pulumi:
                tools.extend(
                    [
                        Tool(
                            name="pulumi_preview",
                            description="Preview Pulumi infrastructure changes",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "code": {"type": "string", "description": "Pulumi Python code"},
                                    "stack_name": {"type": "string", "description": "Name of the Pulumi stack"},
                                    "project_name": {
                                        "type": "string",
                                        "description": "Name of the Pulumi project",
                                        "default": "mcp-project",
                                    },
                                },
                                "required": ["code", "stack_name"],
                            },
                        ),
                        Tool(
                            name="pulumi_up",
                            description="Deploy Pulumi infrastructure",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "code": {"type": "string", "description": "Pulumi Python code"},
                                    "stack_name": {"type": "string", "description": "Name of the Pulumi stack"},
                                    "project_name": {
                                        "type": "string",
                                        "description": "Name of the Pulumi project",
                                        "default": "mcp-project",
                                    },
                                },
                                "required": ["code", "stack_name"],
                            },
                        ),
                    ]
                )

            # Include function management tools if enabled
            if self.config.enable_function_storage:
                tools.extend(
                    [
                        Tool(
                            name="save_function",
                            description="Save a reusable Python function",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Function name"},
                                    "code": {"type": "string", "description": "Function Python code"},
                                    "description": {
                                        "type": "string",
                                        "description": "Function description",
                                        "default": "",
                                    },
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Function tags",
                                        "default": [],
                                    },
                                    "category": {
                                        "type": "string",
                                        "description": "Function category",
                                        "default": "general",
                                    },
                                },
                                "required": ["name", "code"],
                            },
                        ),
                        Tool(
                            name="list_functions",
                            description="List saved functions with optional " "filtering",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "category": {"type": "string", "description": "Filter by category"},
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Filter by tags",
                                    },
                                },
                            },
                        ),
                        Tool(
                            name="delete_function",
                            description="Delete a saved function",
                            inputSchema={
                                "type": "object",
                                "properties": {"name": {"type": "string", "description": "Function name to delete"}},
                                "required": ["name"],
                            },
                        ),
                        Tool(
                            name="execute_with_functions",
                            description="Execute Python code with access to " "saved functions",
                            inputSchema={
                                "type": "object",
                                "properties": {
                                    "code": {
                                        "type": "string",
                                        "description": "Python code that can use " "saved functions",
                                    },
                                    "context": {
                                        "type": "string",
                                        "enum": ["general", "finops", "devops", "security"],
                                        "description": "Execution context",
                                        "default": "general",
                                    },
                                },
                                "required": ["code"],
                            },
                        ),
                    ]
                )

            return tools

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            try:
                if name == "boto3_execute" and self.config.enable_boto3_execution:
                    result = await self._boto3_execute(arguments["code"], arguments.get("context", "general"))
                elif name == "pulumi_preview" and self.config.enable_pulumi:
                    result = await self._pulumi_preview(
                        arguments["code"], arguments["stack_name"], arguments.get("project_name", "mcp-project")
                    )
                elif name == "pulumi_up" and self.config.enable_pulumi:
                    result = await self._pulumi_up(
                        arguments["code"], arguments["stack_name"], arguments.get("project_name", "mcp-project")
                    )
                elif name == "save_function" and self.config.enable_function_storage:
                    result = self.storage.save_function(
                        arguments["name"],
                        arguments["code"],
                        arguments.get("description", ""),
                        arguments.get("tags", []),
                        arguments.get("category", "general"),
                    )
                elif name == "list_functions" and self.config.enable_function_storage:
                    result = self.storage.list_functions(arguments.get("category"), arguments.get("tags"))
                elif name == "delete_function" and self.config.enable_function_storage:
                    result = self.storage.delete_function(arguments["name"])
                elif name == "execute_with_functions" and self.config.enable_function_storage:
                    result = await self._execute_with_functions(arguments["code"], arguments.get("context", "general"))
                else:
                    result = {"error": f"Tool '{name}' is not available or disabled"}

                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            except Exception as e:
                error_result = {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()}
                return [TextContent(type="text", text=json.dumps(error_result, indent=2))]

    async def _boto3_execute(self, code: str, context: str = "general") -> Dict[str, Any]:
        """Execute boto3 code with timeout"""
        # Build execution namespace based on context
        namespace = {
            "boto3": boto3,
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
            "session": self.aws_session,  # Use configured session
            "aws": self.aws_helpers,
            "cost": self.cost_utils,
            "monitoring": self.monitoring_utils,
        }

        # Add context-specific imports
        if context == "finops":
            try:
                import numpy as np
                import pandas as pd

                namespace.update({"pd": pd, "np": np})
            except ImportError:
                pass  # Optional dependencies

        try:
            # Use asyncio.wait_for for timeout
            output_capture = StringIO()
            error_capture = StringIO()

            with redirect_stdout(output_capture), redirect_stderr(error_capture):
                # Execute with timeout
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: exec(code, namespace)),
                    timeout=self.config.execution_timeout,
                )

            output = output_capture.getvalue()
            errors = error_capture.getvalue()

            return {"success": True, "output": output, "errors": errors if errors else None, "context": context}

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Code execution timed out after " f"{self.config.execution_timeout} seconds",
                "error_type": "TimeoutError",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }

    async def _pulumi_preview(self, code: str, stack_name: str, project_name: str) -> Dict[str, Any]:
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

    async def _execute_with_functions(self, code: str, context: str = "general") -> Dict[str, Any]:
        """Execute code with saved functions available"""

        # Get all saved functions
        saved_functions = self.storage.get_all_functions_code()

        # Build namespace with saved functions
        namespace = {
            "boto3": boto3,
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
            "session": self.aws_session,  # Use configured session
            "aws": self.aws_helpers,
            "cost": self.cost_utils,
            "monitoring": self.monitoring_utils,
        }

        # Add saved functions to namespace
        for func_name, func_code in saved_functions.items():
            try:
                exec(func_code, namespace)
                self.storage.update_usage(func_name)
            except Exception as e:
                if self.config.debug:
                    print(f"Warning: Could not load function " f"{func_name}: {e}")

        # Add context-specific imports
        if context == "finops":
            try:
                import numpy as np
                import pandas as pd

                namespace.update({"pd": pd, "np": np})
            except ImportError:
                pass

        try:
            output_capture = StringIO()
            error_capture = StringIO()

            with redirect_stdout(output_capture), redirect_stderr(error_capture):
                # Execute with timeout
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, lambda: exec(code, namespace)),
                    timeout=self.config.execution_timeout,
                )

            output = output_capture.getvalue()
            errors = error_capture.getvalue()

            return {
                "success": True,
                "output": output,
                "errors": errors if errors else None,
                "functions_available": list(saved_functions.keys()),
                "context": context,
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Code execution timed out after " f"{self.config.execution_timeout} seconds",
                "error_type": "TimeoutError",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }

    async def run(self):
        """Run the MCP server"""
        if self.config.debug:
            print("🚀 Starting AWS DevOps MCP Server...")
            print(
                f"🔧 Tools enabled: "
                f"boto3={self.config.enable_boto3_execution}, "
                f"pulumi={self.config.enable_pulumi}, "
                f"functions={self.config.enable_function_storage}"
            )

        async with stdio_server() as streams:
            # Add empty initialization_options parameter
            # as required by newer MCP API
            await self.server.run(streams[0], streams[1], {})


async def main():
    """Main entry point"""
    config = parse_arguments()
    server = AWSDevOpsMCPServer(config)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
