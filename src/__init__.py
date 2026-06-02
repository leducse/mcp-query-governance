"""MCP Query Governance MVP (portfolio).

Local, AWS-native-in-design implementation of:
  * Part 1 - Sentinel: ML query-monitoring + notify-only enforcement.
  * Part 2 - Governed MCP: catalog-driven query execution with RLS injection.

Runs entirely locally (SQLite by default) with no real AWS dependency. See
``README.md`` and ``MVP_SPEC.md`` for scope and the AWS production mapping.
"""

__all__ = ["config"]
