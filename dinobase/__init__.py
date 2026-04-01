"""🦕 Dinobase — the agent-first database."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("dinobase")
except PackageNotFoundError:
    __version__ = "0.0.0.dev0"
