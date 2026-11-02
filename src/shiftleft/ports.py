"""Ports. Engine code depends only on these; each tool lives in exactly one adapter module."""
from typing import Protocol

from .model import Context, ScanResult


class Scanner(Protocol):
    name: str
    stages: tuple            # stages this scanner runs in

    def scan(self, ctx: Context) -> ScanResult: ...
