from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

import numpy as np

from src.branch_sql_MVP.offline import embed
from src.branch_sql_MVP.settings import EmbeddingSettings


def test_dense_passages_serializes_shared_model_inference(monkeypatch):
    state = {"active": 0, "maximum": 0}
    state_lock = Lock()

    class FakeDenseModel:
        def encode(self, texts, **_kwargs):
            with state_lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
            sleep(0.02)
            with state_lock:
                state["active"] -= 1
            return np.ones((len(texts), 2), dtype=np.float32)

    monkeypatch.setattr(embed, "_dense", lambda *_args: FakeDenseModel())
    settings = EmbeddingSettings(device="cpu")

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda text: embed.dense_passages([text], settings), ["a", "b", "c"]))

    assert state["maximum"] == 1
    assert results == [[[1.0, 1.0]], [[1.0, 1.0]], [[1.0, 1.0]]]
