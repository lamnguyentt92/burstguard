# BurstGuard

Mã nguồn thí nghiệm cho nghiên cứu **độ bền của fine-tuning liên kết (federated) các mô hình nền chuỗi thời gian tí hon
(Tiny Time Mixers, TTM-R2) cho dự báo lưu lượng di động** trên dữ liệu Telecom Italia — Milan, chạy bằng Flower trên CPU.
Mục tiêu: bài nộp collection *Trustworthy and Efficient Time-Series Intelligence at the Mobile Edge* (Mobile Networks and Applications, Springer).

## Phiên bản

| Phiên bản | Nội dung | Hướng dẫn (tiếng Việt) |
|---|---|---|
| **v0.1.0** (hiện tại) | Môi trường ảo cô lập, pipeline dữ liệu Milan, TTM-R2, baseline, FL sạch (FedAvg × 4 chế độ fine-tune), gom log | [docs/README_v0.1.0.md](docs/README_v0.1.0.md) |
| v0.2.0 (dự kiến) | Đánh giá độ bền: phòng thủ BurstGuard tương thích SecAgg+, các phương pháp tổng hợp bền, kịch bản kiểm thử | — |

Lịch sử thay đổi: [CHANGELOG.md](CHANGELOG.md). Phiên bản đang dùng: `cat VERSION` hoặc `burstguard --version`.

## Bắt đầu nhanh

```bash
git clone https://github.com/lamnguyentt92/burstguard.git && cd burstguard
git checkout v0.1.0
bash scripts/setup_venv.sh          # tạo .venv cô lập trong dự án (không cần sudo)
source .venv/bin/activate
burstguard doctor && burstguard smoke
bash scripts/collect_logs.sh        # gom log (thành công hay thất bại) -> reports/bg_report_*.txt
```

Chi tiết từng bước, cấu hình và cách gửi log: **[docs/README_v0.1.0.md](docs/README_v0.1.0.md)**.

## Dữ liệu & giấy phép

- Dữ liệu: Barlacchi et al., *A multi-source dataset of urban life in the city of Milan and the Province of Trentino*,
  Scientific Data 2, 150055 (2015) — giấy phép ODbL. Không kèm trong repo; tải bằng `burstguard data download`.
- Mô hình: IBM Granite TinyTimeMixers R2 (`ibm-granite/granite-timeseries-ttm-r2`, Apache-2.0), tải lúc chạy.
