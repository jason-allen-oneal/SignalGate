from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .errors import SGError


class Embedder(Protocol):
    dim: int

    async def embed(self, text: str) -> np.ndarray: ...


@dataclass
class HashEmbedder:
    """Deterministic local embedder for tests and dry runs.

    Model path format: `test-hash:<dim>`
    """

    dim: int = 64

    async def embed(self, text: str) -> np.ndarray:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = bytearray()
        while len(raw) < self.dim:
            raw.extend(h)
            h = hashlib.sha256(h).digest()
        v = np.frombuffer(bytes(raw[: self.dim]), dtype=np.uint8).astype(np.float32)
        v = v - v.mean()
        n = float(np.linalg.norm(v))
        return v if n == 0 else (v / n)


@dataclass
class LocalLlamaCppEmbedder:
    model_path: str
    n_threads: int | None = None

    def __post_init__(self) -> None:
        # Import here so base tests can run without the compiled dependency.
        try:
            from llama_cpp import Llama  # type: ignore
        except Exception as e:
            raise SGError(
                code="SG_INTERNAL",
                message=(
                    f"llama-cpp-python not available ({e}). "
                    "Install with: uv sync --extra embed"
                ),
                status_code=500,
                retryable=False,
            ) from e

        if not self.model_path:
            raise SGError(
                code="SG_INTERNAL", message="Missing embedding model path", status_code=500
            )
        if not os.path.exists(self.model_path):
            raise SGError(
                code="SG_INTERNAL",
                message=f"Embedding model not found at {self.model_path}",
                status_code=500,
                retryable=False,
            )

        self._llm = Llama(
            model_path=self.model_path,
            embedding=True,
            n_threads=self.n_threads or max(1, (os.cpu_count() or 2) - 1),
        )

        # Probe dim
        vec = self._embed_sync("test")
        self.dim = int(vec.shape[0])

    def _embed_sync(self, text: str) -> np.ndarray:
        out = self._llm.create_embedding(text)
        data = out.get("data")
        if not data:
            raise SGError(
                code="SG_EMBEDDING_FAILED",
                message="No embedding returned",
                status_code=503,
                retryable=True,
            )
        emb = data[0].get("embedding")
        if not isinstance(emb, list):
            raise SGError(
                code="SG_EMBEDDING_FAILED",
                message="Invalid embedding type",
                status_code=503,
                retryable=True,
            )
        v = np.asarray(emb, dtype=np.float32)
        n = np.linalg.norm(v)
        return v if n == 0 else (v / n)

    async def embed(self, text: str) -> np.ndarray:
        import anyio

        return await anyio.to_thread.run_sync(self._embed_sync, text)


def build_embedder(model_path: str) -> Embedder:
    if model_path.startswith("test-hash:"):
        try:
            dim = int(model_path.split(":", 1)[1])
        except Exception:
            dim = 64
        return HashEmbedder(dim=dim)
    return LocalLlamaCppEmbedder(model_path=model_path)
