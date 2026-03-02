from __future__ import annotations

import numpy as np

from signalgate.classifier import KNNTierClassifier


def test_knn_predict_top2_margin():
    # Two obvious clusters in 3D, already normalized.
    vecs = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    # normalize
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    clf = KNNTierClassifier(vectors=vecs, labels=["budget", "budget", "premium"])  # type: ignore

    q = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    q = q / np.linalg.norm(q)
    res = clf.predict(q, sim_threshold=0.0, margin_threshold=0.0)

    assert res.tier == "budget"
    assert res.top1 >= res.top2
    assert res.margin == res.top1 - res.top2
