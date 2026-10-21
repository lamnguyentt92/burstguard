"""Nạp TinyTimeMixer (TTM), cấu hình chế độ fine-tune, trao đổi tham số train được với Flower,
dự báo theo lô và đường tắt head-only có cache."""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch

log = logging.getLogger("burstguard.model")

FREQ_ALIASES = {"10min": "10min", "10t": "10min", "10m": "10min"}


@dataclass
class ModelInfo:
    source: str
    revision: str
    context_length: int
    prediction_length: int
    horizon: int
    freq_prefix: bool
    n_params: int


def _random_ttm(L: int, H: int, size: str = "small"):
    from tsfm_public.models.tinytimemixer import TinyTimeMixerConfig, TinyTimeMixerForPrediction
    patch = 64 if L % 64 == 0 else next(p for p in (32, 16, 8, 4, 2) if L % p == 0)
    pl = 48 if H <= 48 else 96
    dims = {"small": (256, 2, 128, 2), "tiny": (64, 1, 32, 1)}.get(size, (256, 2, 128, 2))
    cfg = TinyTimeMixerConfig(
        context_length=L, prediction_length=pl, prediction_filter_length=H,
        patch_length=patch, patch_stride=patch, d_model=dims[0], num_layers=dims[1],
        adaptive_patching_levels=3 if dims[0] >= 128 else 0,
        decoder_d_model=dims[2], decoder_num_layers=dims[3], num_input_channels=1,
        resolution_prefix_tuning=True, scaling="std")
    return TinyTimeMixerForPrediction(cfg)


def load_model(cfg: dict[str, Any], seed: int = 0):
    """Trả về (model, ModelInfo). Mô hình ở chế độ eval, mọi tham số requires_grad=False."""
    mcfg, dcfg = cfg["model"], cfg["data"]
    L, H = int(dcfg["context"]), int(dcfg["horizon"])
    src = mcfg["source"]
    torch.manual_seed(seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if src == "random":
            model, rev = _random_ttm(L, H, mcfg.get("random_size", "small")), "random-init"
        elif src in ("hf", "local"):
            from tsfm_public.toolkit.get_model import get_model
            path = mcfg["path"]
            rev = mcfg.get("revision", "auto") or "auto"
            if rev == "auto":
                key = get_model(path, context_length=L, prediction_length=H, return_model_key=True) \
                    if src == "hf" else "local"
                model = get_model(path, context_length=L, prediction_length=H)
                rev = str(key)
            else:
                from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction
                model = TinyTimeMixerForPrediction.from_pretrained(path, revision=rev,
                                                                   prediction_filter_length=H)
        else:
            raise ValueError(f"model.source không hợp lệ: {src}")
    if int(model.config.context_length) != L:
        raise ValueError(f"Mô hình có context_length={model.config.context_length} khác data.context={L}. "
                         f"Đặt data.context cho khớp hoặc chọn model.revision khác.")
    model.eval()
    for p in model.parameters():
        p.requires_grad_(False)
    info = ModelInfo(source=src, revision=rev, context_length=L,
                     prediction_length=int(model.config.prediction_length), horizon=H,
                     freq_prefix=bool(getattr(model.config, "resolution_prefix_tuning", False)),
                     n_params=sum(p.numel() for p in model.parameters()))
    return model, info


# ---------------- dự báo ----------------

def _freq_token(model, n: int, freq: str = "10min") -> torch.Tensor | None:
    base = getattr(model, "base_model", None)
    conf = getattr(model, "config", None) or getattr(base, "config", None)
    if conf is None or not getattr(conf, "resolution_prefix_tuning", False):
        return None
    from tsfm_public.toolkit.time_series_preprocessor import DEFAULT_FREQUENCY_MAPPING
    code = DEFAULT_FREQUENCY_MAPPING.get(FREQ_ALIASES.get(freq.lower(), freq), 0)
    return torch.full((n,), int(code), dtype=torch.long)


def forward(model, X: torch.Tensor, freq: str = "10min") -> torch.Tensor:
    """X [B, L, 1] -> dự báo [B, H, 1] (đơn vị gốc)."""
    ft = _freq_token(model, X.shape[0], freq)
    out = model(past_values=X, freq_token=ft) if ft is not None else model(past_values=X)
    return out.prediction_outputs


@torch.no_grad()
def predict(model, X: np.ndarray, batch: int = 256, freq: str = "10min") -> np.ndarray:
    model.eval()
    outs = []
    for i in range(0, len(X), batch):
        xb = torch.from_numpy(np.ascontiguousarray(X[i:i + batch]))
        outs.append(forward(model, xb, freq).numpy())
    H = outs[0].shape[1] if outs else 0
    return np.concatenate(outs) if outs else np.zeros((0, H, 1), np.float32)


# ---------------- chế độ fine-tune ----------------

def _ttm_core(model):
    """Mô hình TTM bên trong (bỏ lớp bọc peft nếu có)."""
    return model.get_base_model() if hasattr(model, "get_base_model") else model


def configure_peft(model, cfg: dict[str, Any]):
    """Bật requires_grad theo train.peft. Trả về mô hình (có thể đã bọc LoRA)."""
    mode = cfg["train"]["peft"]
    for p in model.parameters():
        p.requires_grad_(False)
    if mode == "head":
        for p in model.head.parameters():
            p.requires_grad_(True)
    elif mode == "decoder":
        for mod in (model.decoder, model.head):
            for p in mod.parameters():
                p.requires_grad_(True)
    elif mode == "full":
        for p in model.parameters():
            p.requires_grad_(True)
    elif mode == "lora":
        from peft import LoraConfig, get_peft_model
        lcfg = LoraConfig(r=int(cfg["train"]["lora_r"]), lora_alpha=int(cfg["train"]["lora_alpha"]),
                          target_modules=["fc1", "fc2"], lora_dropout=0.0, bias="none",
                          modules_to_save=["head"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = get_peft_model(model, lcfg)
    else:
        raise ValueError(mode)
    return model


def trainable_named(model) -> list[tuple[str, torch.nn.Parameter]]:
    return sorted(((n, p) for n, p in model.named_parameters() if p.requires_grad), key=lambda t: t[0])


def get_trainable(model) -> list[np.ndarray]:
    return [p.detach().cpu().numpy().astype(np.float32, copy=True) for _, p in trainable_named(model)]


def set_trainable(model, arrays: list[np.ndarray]) -> None:
    named = trainable_named(model)
    if len(named) != len(arrays):
        raise ValueError(f"Số mảng tham số không khớp: mô hình {len(named)} vs nhận {len(arrays)}")
    with torch.no_grad():
        for (n, p), a in zip(named, arrays):
            a = np.asarray(a, dtype=np.float32)
            if a.size != p.numel():
                raise ValueError(f"Kích thước {n} không khớp: {tuple(p.shape)} vs {a.shape}")
            p.copy_(torch.from_numpy(a.reshape(p.shape)))


def n_trainable(model) -> int:
    return sum(p.numel() for _, p in trainable_named(model))


# ---------------- head-only có cache ----------------

@dataclass
class HeadCache:
    dec: torch.Tensor   # đầu ra decoder [N, C, P, D]
    loc: torch.Tensor
    scale: torch.Tensor
    X: torch.Tensor     # ngữ cảnh gốc (head cần past_values)


@torch.no_grad()
def build_head_cache(model, X: np.ndarray, batch: int = 256, freq: str = "10min") -> HeadCache:
    core = _ttm_core(model)
    core.eval()
    decs, locs, scales = [], [], []
    for i in range(0, len(X), batch):
        xb = torch.from_numpy(np.ascontiguousarray(X[i:i + batch]))
        ft = _freq_token(core, xb.shape[0], freq)
        out = core(past_values=xb, freq_token=ft) if ft is not None else core(past_values=xb)
        if out.decoder_hidden_state is None:
            raise RuntimeError("Mô hình không trả decoder_hidden_state (light_mode?) — tắt train.head_cache")
        decs.append(out.decoder_hidden_state); locs.append(out.loc); scales.append(out.scale)
    return HeadCache(torch.cat(decs), torch.cat(locs), torch.cat(scales),
                     torch.from_numpy(np.ascontiguousarray(X)))


def head_forward(model, cache: HeadCache, idx: torch.Tensor, H: int) -> torch.Tensor:
    core = _ttm_core(model)
    y = core.head(cache.dec[idx], past_values=cache.X[idx])
    if isinstance(y, tuple):
        y = y[0]
    y = y[:, :H, :]
    return core.backbone.scaler.inverse(data=y, loc=cache.loc[idx], scale=cache.scale[idx])


@torch.no_grad()
def check_head_cache(model, X: np.ndarray, H: int, freq: str = "10min", tol: float = 1e-4) -> float:
    """So khớp đường tắt cache với forward đầy đủ trên vài cửa sổ. Trả về sai lệch tương đối lớn nhất."""
    Xs = X[: min(8, len(X))]
    cache = build_head_cache(model, Xs, freq=freq)
    core = _ttm_core(model)
    core.eval()
    a = head_forward(model, cache, torch.arange(len(Xs)), H)
    b = forward(core, torch.from_numpy(np.ascontiguousarray(Xs)), freq)
    rel = float((a - b).abs().max() / (b.abs().max() + 1e-8))
    return rel
