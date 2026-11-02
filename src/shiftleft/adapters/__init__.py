"""Adapter registry. The engine picks adapters by name from this table; nothing else imports a tool."""
from . import (bundle_rules, complexipy, costlens, gitleaks, nbstripout, osv, purity_adapter, pyspark_antipattern, repo_checks, ruff,
               sparkdoctor, sqlfluff, sqlglot_rules, vulture)

REGISTRY = {m.NAME: m for m in (ruff, sqlfluff, sqlglot_rules, costlens, sparkdoctor, pyspark_antipattern, bundle_rules, purity_adapter,
                                gitleaks, osv, vulture, complexipy, nbstripout, repo_checks)}
