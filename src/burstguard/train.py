"""Vòng huấn luyện cục bộ của một site (dùng trong client Flower và trong baseline cục bộ/tập trung)."""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import torch

from burstguard import model as M


def local_train(model, X: np.ndarray, Y: np.ndarray, scale: float, cfg: dict[str, Any],
                seed: int = 0, cache: "M.HeadCache | None" = None) -> dict[str, float]:
    """Huấn luyện tại chỗ các tham số requires_grad. Loss = MSE trên giá trị chuẩn hoá theo độ lệch
    chuẩn train của site (để các site có thang đo khác nhau đóng góp cân bằng)."""
    tcfg = cfg["train"]
    H = Y.shape[1]
    params = [p for _, p in M.trainable_named(model)]
    if not params:
        raise RuntimeError("Không có tham số nào để huấn luyện — kiểm tra train.peft")
    opt = torch.optim.AdamW(params, lr=float(tcfg["lr"]), weight_decay=float(tcfg["weight_decay"]))
    g = torch.Generator().manual_seed(int(seed))
    Yt = torch.from_numpy(np.ascontiguousarray(Y))
    Xt = torch.from_numpy(np.ascontiguousarray(X))
    bs = int(tcfg["batch_size"])
    inv = 1.0 / float(scale)
    use_cache = cache is not None
    if use_cache:
        M._ttm_core(model).eval()          # backbone/decoder đông cứng: chỉ head ở chế độ train
        M._ttm_core(model).head.train()
    else:
        model.train()
    t0 = time.process_time()
    tot, nb = 0.0, 0
    for _ in range(int(tcfg["local_epochs"])):
        perm = torch.randperm(len(X), generator=g)
        for i in range(0, len(X), bs):
            idx = perm[i:i + bs]
            pred = M.head_forward(model, cache, idx, H) if use_cache else M.forward(model, Xt[idx], cfg["model"]["freq"])
            loss = torch.mean(((pred - Yt[idx]) * inv) ** 2)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            tot += float(loss.detach()); nb += 1
    model.eval()
    return {"train_loss": tot / max(nb, 1), "train_batches": nb, "train_cpu_s": time.process_time() - t0}
