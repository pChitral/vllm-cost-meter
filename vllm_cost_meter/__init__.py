"""vllm-cost-meter — live effective cost-per-million-tokens meter for vLLM servers."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vllm-cost-meter")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
