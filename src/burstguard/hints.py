"""Gợi ý khắc phục theo loại lỗi (in ra khi chạy thất bại và ghi vào summary.json)."""
from __future__ import annotations

import traceback


def hint_for(exc: BaseException) -> str | None:
    chain = []
    e: BaseException | None = exc
    while e is not None and len(chain) < 8:
        chain.append(e)
        e = e.__cause__ or e.__context__
    names = " ".join(type(x).__name__ for x in chain)
    text = " ".join(str(x) for x in chain)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    low = (names + " " + text + " " + tb).lower()

    if "huggingface" in low and any(k in low for k in ("proxyerror", "connecterror", "connectionerror", "timeout",
                                                         "403", "offline", "localentrynotfound", "name resolution")):
        return ("Không tải được mô hình từ Hugging Face. Kiểm tra `burstguard doctor` (mục net:huggingface). "
                "Cách khác: chạy `burstguard model-download` trên máy có mạng rồi chép thư mục .cache/huggingface "
                "sang VM; hoặc dùng --set model.source=random để thử pipeline.")
    if "không thấy dữ liệu" in low or ("filenotfounderror" in low and ".npz" in low):
        return ("Chưa có dữ liệu đã xử lý. Thử nhanh: `burstguard data synthetic` rồi --set data.path=\"data/processed/synthetic.npz\". "
                "Dữ liệu thật: `burstguard data download` rồi `burstguard data prepare`.")
    if "dataverse" in low and any(k in low for k in ("connection", "proxy", "timeout", "403", "ssl")):
        return ("Không truy cập được Harvard Dataverse từ máy này. Tải thủ công các file sms-call-internet-mi-*.txt "
                "trên trình duyệt và chép vào data/raw/milan/, rồi chạy `burstguard data prepare`.")
    if any(k in low for k in ("out of memory", "outofmemory", "memoryerror", "oom", "killed", "worker crashed",
                              "actor died", "raylet")):
        return ("Có dấu hiệu thiếu RAM / worker Ray bị kill. Giảm số client chạy song song: --set sim.num_cpus=2 "
                "(hoặc tăng sim.cpus_per_client), hoặc giảm data.num_sites; kiểm tra `free -h`.")
    if "context_length" in low and "khác data.context" in low:
        return "Ngữ cảnh mô hình và dữ liệu không khớp — đặt data.context=512 hoặc chọn model.revision phù hợp."
    if "client lỗi" in low:
        return "Một hoặc nhiều client lỗi — xem các dòng '[client N] LỖI trong fit' trong console.log."
    if "modulenotfounderror" in low or "importerror" in low:
        return "Thiếu thư viện — chạy lại `bash scripts/setup_venv.sh` và đảm bảo đã `source .venv/bin/activate`."
    return None
