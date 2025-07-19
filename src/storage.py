"""
Storage module for managing user-defined functions in SQLite database
"""

import ast
import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional


class FunctionStorage:
    """Manages storage and retrieval of user-defined functions"""

    def __init__(self, db_path: str = "functions.db", max_functions: int = 20):
        self.db_path = db_path
        self.max_functions = max_functions
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with functions table"""
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS functions (
                    name TEXT PRIMARY KEY,
                    code TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    category TEXT DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    last_used TEXT,
                    usage_count INTEGER DEFAULT 0,
                    version INTEGER DEFAULT 1
                )
            """
            )
            conn.commit()

    def save_function(
        self, name: str, code: str, description: str = "", tags: List[str] = None, category: str = "general"
    ) -> Dict[str, Any]:
        """Save a new function or update existing one"""
        if tags is None:
            tags = []

        # Validate syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {"success": False, "error": f"Syntax error: {e}"}

        # Check function limit for new functions
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Check if function exists
            cursor.execute("SELECT name FROM functions WHERE name = ?", (name,))
            exists = cursor.fetchone() is not None

            if not exists:
                # Check function count limit
                cursor.execute("SELECT COUNT(*) FROM functions")
                count = cursor.fetchone()[0]

                if count >= self.max_functions:
                    return {
                        "success": False,
                        "error": f"Maximum function limit ({self.max_functions}) reached. Delete a function first.",
                    }

            # Save/update function
            cursor.execute(
                """
                INSERT OR REPLACE INTO functions 
                (name, code, description, tags, category, created_at, version)
                VALUES (?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT version + 1 FROM functions WHERE name = ?), 1))
            """,
                (name, code, description, json.dumps(tags), category, datetime.now().isoformat(), name),
            )

            conn.commit()

        return {"success": True, "message": f"Function '{name}' saved successfully", "function_name": name}

    def list_functions(self, category: str = None, tags: List[str] = None) -> Dict[str, Any]:
        """List all saved functions with optional filters"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM functions"
            params = []

            if category:
                query += " WHERE category = ?"
                params.append(category)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            functions = []
            for row in rows:
                func_data = {
                    "name": row[0],
                    "description": row[2],
                    "tags": json.loads(row[3]),
                    "category": row[4],
                    "created_at": row[5],
                    "last_used": row[6],
                    "usage_count": row[7],
                    "version": row[8],
                }

                # Filter by tags if specified
                if tags and not any(tag in func_data["tags"] for tag in tags):
                    continue

                functions.append(func_data)

        return {"functions": functions, "total": len(functions), "limit": self.max_functions}

    def get_function(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific function by name"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM functions WHERE name = ?", (name,))
            row = cursor.fetchone()

            if row:
                return {
                    "name": row[0],
                    "code": row[1],
                    "description": row[2],
                    "tags": json.loads(row[3]),
                    "category": row[4],
                    "created_at": row[5],
                    "last_used": row[6],
                    "usage_count": row[7],
                    "version": row[8],
                }
            return None

    def delete_function(self, name: str) -> Dict[str, Any]:
        """Delete a function by name"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM functions WHERE name = ?", (name,))

            if cursor.rowcount > 0:
                conn.commit()
                return {"success": True, "message": f"Function '{name}' deleted successfully"}
            else:
                return {"success": False, "error": f"Function '{name}' not found"}

    def update_usage(self, name: str):
        """Update usage statistics for a function"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE functions 
                SET usage_count = usage_count + 1, last_used = ? 
                WHERE name = ?
            """,
                (datetime.now().isoformat(), name),
            )
            conn.commit()

    def get_all_functions_code(self) -> Dict[str, str]:
        """Get all function codes for execution namespace"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, code FROM functions")
            return {row[0]: row[1] for row in cursor.fetchall()}
