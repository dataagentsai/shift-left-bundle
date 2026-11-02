"""Adapter registry. The engine picks adapters by name from this table; nothing else imports a tool."""
from . import complexipy, gitleaks, nbstripout, osv, repo_checks, ruff, sqlfluff, vulture

REGISTRY = {m.NAME: m for m in (ruff, sqlfluff, gitleaks, osv, vulture, complexipy, nbstripout, repo_checks)}
