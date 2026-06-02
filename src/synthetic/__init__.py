"""Synthetic query-audit-log generation (no real data, no live cloud)."""

from .generator import GeneratedAudit, generate_audit_log

__all__ = ["GeneratedAudit", "generate_audit_log"]
