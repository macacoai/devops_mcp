import ast


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
