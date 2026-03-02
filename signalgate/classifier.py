from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from .errors import SGError

Tier = Literal["budget", "balanced", "premium"]


@dataclass(frozen=True)
class KNNResult:
    tier: Tier
    top1: float
    top2: float
    margin: float


@dataclass
class KNNTierClassifier:
    vectors: np.ndarray  # shape (n, d), normalized
    labels: list[Tier]

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "KNNTierClassifier":
        p = Path(path)
        if not p.exists():
            raise SGError(
                code="SG_CLASSIFIER_FAILED",
                message=f"KNN dataset not found: {p}",
                status_code=503,
                retryable=True,
            )

        vecs: list[np.ndarray] = []
        labels: list[Tier] = []

        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            label = rec.get("label")
            emb = rec.get("embedding")
            if label not in ("budget", "balanced", "premium"):
                continue
            if not isinstance(emb, list) or len(emb) < 8:
                continue
            v = np.asarray(emb, dtype=np.float32)
            n = np.linalg.norm(v)
            v = v if n == 0 else (v / n)
            vecs.append(v)
            labels.append(label)

        if not vecs:
            raise SGError(
                code="SG_CLASSIFIER_FAILED",
                message="Empty KNN dataset",
                status_code=503,
                retryable=True,
            )

        mat = np.vstack(vecs)
        return cls(vectors=mat, labels=labels)

    def predict(
        self, query_vec: np.ndarray, *, sim_threshold: float, margin_threshold: float
    ) -> KNNResult:
        if query_vec.ndim != 1:
            raise SGError(
                code="SG_CLASSIFIER_FAILED",
                message="Invalid query embedding",
                status_code=503,
                retryable=True,
            )

        # Assume all vectors normalized -> dot product == cosine similarity.
        sims = self.vectors @ query_vec.astype(np.float32)
        if sims.size == 0:
            raise SGError(
                code="SG_CLASSIFIER_FAILED", message="No vectors", status_code=503, retryable=True
            )

        # Find top2 indices.
        if sims.size == 1:
            i1 = int(np.argmax(sims))
            top1 = float(sims[i1])
            top2 = -1.0
            margin = 1.0
            tier: Tier = self.labels[i1]
        else:
            if sims.size == 2:
                idx = np.argsort(-sims)[:2]
            else:
                idx = np.argpartition(-sims, 1)[:2]
                idx = idx[np.argsort(-sims[idx])]
            i1, i2 = int(idx[0]), int(idx[1])
            top1, top2 = float(sims[i1]), float(sims[i2])
            margin = float(top1 - top2)
            tier = self.labels[i1]

        # Caller handles promotion; return raw similarity stats too.
        return KNNResult(tier=tier, top1=top1, top2=top2, margin=margin)
