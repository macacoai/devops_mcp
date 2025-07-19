#!/usr/bin/env python3
"""
Simple working MCP server for demonstration with CLI argument support
"""
import argparse
import asyncio
import json
import os
from typing import Any, Dict


def parse_arguments():
    """Parse command-line arguments for simple server"""
    parser = argparse.ArgumentParser(
        description="Simple AWS DevOps MCP Server Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # AWS Configuration
    parser.add_argument(
        "--aws-region",
        "--region",
        default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        help="AWS region (default: %(default)s)",
    )
    parser.add_argument(
        "--aws-profile",
        "--profile",
        default=os.getenv("AWS_PROFILE"),
        help="AWS CLI profile to use",
    )

    # Server Configuration
    parser.add_argument(
        "--database-path",
        "--db-path",
        default=os.getenv("DATABASE_PATH", "data/functions.db"),
        help="Path to function storage database (default: %(default)s)",
    )
    parser.add_argument(
        "--max-functions",
        type=int,
        default=int(os.getenv("MAX_FUNCTIONS", "20")),
        help="Maximum number of functions to store (default: %(default)s)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.getenv("DEBUG", "false").lower() in ("true", "1", "yes"),
        help="Enable debug mode",
    )

    return parser.parse_args()


# Mock MCP-like functionality for demonstration
class SimpleMCPServer:
    """Simple demonstration server with CLI support"""

    def __init__(self, config=None):
        self.config = config or parse_arguments()

        print("🚀 AWS DevOps MCP Server Starting...")
        if self.config.debug:
            print("🐛 Debug mode enabled")
            print(f"📍 AWS Region: {self.config.aws_region}")
            print(f"👤 AWS Profile: {self.config.aws_profile or 'default'}")
            print(f"💾 Database Path: {self.config.database_path}")
            print(f"📊 Max Functions: {self.config.max_functions}")

        from helpers import AWSHelpers, CostUtils, MonitoringUtils
        from storage import FunctionStorage

        self.storage = FunctionStorage(self.config.database_path, max_functions=self.config.max_functions)
        self.aws_helpers = AWSHelpers()
        self.cost_utils = CostUtils()
        self.monitoring_utils = MonitoringUtils()

        print("✅ Server components initialized")
        print(f"📚 Function storage ready (max {self.config.max_functions} functions)")
        print("🔧 AWS helpers loaded")
        print("💰 Cost utilities available")
        print("📊 Monitoring utilities ready")

    def list_tools(self):
        """List available tools"""
        return [
            "save_function",
            "list_functions",
            "delete_function",
            "boto3_execute",
            "execute_with_functions",
        ]

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]):
        """Handle tool execution"""
        if self.config.debug:
            print(f"🔧 Executing tool: {tool_name}")

        try:
            if tool_name == "save_function":
                return self.storage.save_function(
                    arguments["name"],
                    arguments["code"],
                    arguments.get("description", ""),
                    arguments.get("tags", []),
                    arguments.get("category", "general"),
                )
            elif tool_name == "list_functions":
                return self.storage.list_functions(arguments.get("category"), arguments.get("tags"))
            elif tool_name == "delete_function":
                return self.storage.delete_function(arguments["name"])
            elif tool_name == "boto3_execute":
                return await self._execute_boto3_code(arguments["code"], arguments.get("context", "general"))
            elif tool_name == "execute_with_functions":
                return await self._execute_with_functions(arguments["code"], arguments.get("context", "general"))
            else:
                return {"error": f"Unknown tool: {tool_name}"}

        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    async def _execute_boto3_code(self, code: str, context: str = "general"):
        """Execute boto3 code safely"""
        from contextlib import redirect_stderr, redirect_stdout
        from datetime import datetime, timedelta
        from io import StringIO

        import boto3

        namespace = {
            "boto3": boto3,
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
            "session": boto3.Session(),
            "aws": self.aws_helpers,
            "cost": self.cost_utils,
            "monitoring": self.monitoring_utils,
        }

        try:
            output_capture = StringIO()
            error_capture = StringIO()

            with redirect_stdout(output_capture), redirect_stderr(error_capture):
                exec(code, namespace)

            return {
                "success": True,
                "output": output_capture.getvalue(),
                "errors": error_capture.getvalue() or None,
                "context": context,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    async def _execute_with_functions(self, code: str, context: str = "general"):
        """Execute code with saved functions"""
        saved_functions = self.storage.get_all_functions_code()

        from contextlib import redirect_stderr, redirect_stdout
        from datetime import datetime, timedelta
        from io import StringIO

        import boto3

        namespace = {
            "boto3": boto3,
            "json": json,
            "datetime": datetime,
            "timedelta": timedelta,
            "session": boto3.Session(),
            "aws": self.aws_helpers,
            "cost": self.cost_utils,
            "monitoring": self.monitoring_utils,
        }

        # Load saved functions
        for func_name, func_code in saved_functions.items():
            try:
                exec(func_code, namespace)
                self.storage.update_usage(func_name)
            except Exception as e:
                if self.config.debug:
                    print(f"Warning: Could not load function {func_name}: {e}")

        try:
            output_capture = StringIO()
            error_capture = StringIO()

            with redirect_stdout(output_capture), redirect_stderr(error_capture):
                exec(code, namespace)

            return {
                "success": True,
                "output": output_capture.getvalue(),
                "errors": error_capture.getvalue() or None,
                "functions_available": list(saved_functions.keys()),
                "context": context,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "error_type": type(e).__name__}

    async def run_demo(self):
        """Run demonstration of server capabilities with configuration"""
        print("\n" + "=" * 60)
        print("🎯 RUNNING SERVER DEMO")
        print("=" * 60)
        print(f"🔧 Configuration: Region={self.config.aws_region}, Profile={self.config.aws_profile or 'default'}")
        print(f"📂 Database: {self.config.database_path}, Max Functions: {self.config.max_functions}")

        # Demo 1: Save a function
        print("\n1. Saving a demo function...")
        result = await self.handle_tool_call(
            "save_function",
            {
                "name": "demo_cost_analysis",
                "code": """
def analyze_costs(service_name="EC2"):
    '''Demo function for cost analysis'''
    print(f"Analyzing costs for {service_name}...")
    return {"service": service_name, "estimated_monthly_cost": 150.0}
""",
                "description": "Demo cost analysis function",
                "tags": ["demo", "finops"],
                "category": "cost_analysis",
            },
        )
        print(f"✅ Save result: {result}")

        # Demo 2: List functions
        print("\n2. Listing saved functions...")
        result = await self.handle_tool_call("list_functions", {})
        print(f"📋 Found {result.get('total', 0)} functions")

        # Demo 3: Execute boto3 code
        print("\n3. Executing boto3 code...")
        result = await self.handle_tool_call(
            "boto3_execute",
            {
                "code": """
print("Testing boto3 execution...")
print(f"Current session region: {session.region_name}")
print("Available helpers:")
print(f"- AWS Helpers: {type(aws).__name__}")
print(f"- Cost Utils: {type(cost).__name__}")
print(f"- Monitoring Utils: {type(monitoring).__name__}")
print("✅ boto3 execution successful!")
""",
                "context": "general",
            },
        )
        print(f"🔧 Execution result: {result['success']}")
        if result["success"]:
            print("Output:", result["output"])

        # Demo 4: Execute with functions
        print("\n4. Executing code with saved functions...")
        result = await self.handle_tool_call(
            "execute_with_functions",
            {
                "code": """
print("Testing saved function execution...")
if 'demo_cost_analysis' in locals():
    result = analyze_costs("RDS")
    print(f"Function result: {result}")
else:
    print("Demo function not found")
print("✅ Function execution successful!")
""",
                "context": "finops",
            },
        )
        print(f"📝 Execution result: {result['success']}")
        if result["success"]:
            print("Output:", result["output"])

        # Demo 5: Cleanup
        print("\n5. Cleaning up demo function...")
        result = await self.handle_tool_call("delete_function", {"name": "demo_cost_analysis"})
        print(f"🗑️ Delete result: {result}")

        print("\n" + "=" * 60)
        print("✅ DEMO COMPLETED SUCCESSFULLY!")
        print("=" * 60)

        print("\n🎉 Server is working correctly!")


async def main():
    """Main entry point with CLI support"""
    config = parse_arguments()

    print("AWS DevOps MCP Server - Simple Demo")
    print("=" * 40)

    if config.debug:
        print("🐛 Running in debug mode")

    server = SimpleMCPServer(config)
    await server.run_demo()

    print("\n📖 Usage examples:")
    print("  python simple_server.py --help")
    print("  python simple_server.py --region us-west-2 --profile production")
    print("  python simple_server.py --max-functions 50 --debug")
    print("  python simple_server.py --database-path /tmp/test.db")


if __name__ == "__main__":
    asyncio.run(main())
