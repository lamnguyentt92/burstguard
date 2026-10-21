# BurstGuard

Mã nguồn thí nghiệm cho nghiên cứu **độ bền của fine-tuning liên kết (federated) các mô hình nền chuỗi thời gian tí hon
(Tiny Time Mixers, TTM-R2) cho dự báo lưu lượng di động trước backdoor kích hoạt bằng burst**, kèm phòng thủ
**BurstGuard** tương thích secure aggregation. Dữ liệu Telecom Italia — Milan; chạy bằng Flower trên CPU.
Mục tiêu: bài nộp collection *Trustworthy and Efficient Time-Series Intelligence at the Mobile Edge*
(Mobile Networks and Applications, Springer).

## Phiên bản

| Phiên bản | Nội dung | Hướng dẫn (tiếng Việt) |
|---|---|---|
| **v0.2.0** (hiện tại) | Khung thí nghiệm đủ cho bài báo: 5 tấn công, 9 phòng thủ + BurstGuard, SecAgg+ thật (Flower) và SecAgg theo nhóm, lưới E0–E8 chia shard cho 5 VM, phân tích thống kê ra bảng/hình; log tiếng Anh có số phiên bản; cô lập theo phiên bản | [docs/README_v0.2.0.md](docs/README_v0.2.0.md) |
| v0.1.1 | v0.1.0 + tắt telemetry Flower; đánh dấu phiên bản bằng nhánh `release/vX.Y.Z` | [docs/README_v0.1.1.md](docs/README_v0.1.1.md) |
| v0.1.0 | Môi trường ảo cô lập, pipeline dữ liệu Milan, TTM-R2, baseline, FL sạch (FedAvg × 4 chế độ fine-tune), gom log | [docs/README_v0.1.0.md](docs/README_v0.1.0.md) |
| v0.3.0 (dự kiến) | Triển khai Flower thật trên 5 VM (SuperLink/SuperNode), mô phỏng mạng, đo chi phí hệ thống | — |

Mỗi phiên bản có nhánh `release/vX.Y.Z`; `main` luôn là bản mới nhất. Lịch sử thay đổi (tiếng Anh): [CHANGELOG.md](CHANGELOG.md).
Phiên bản đang dùng: `cat VERSION` hoặc `burstguard --version`.

## Bắt đầu nhanh (mỗi phiên bản một thư mục riêng — không đè bản cũ)

```bash
git clone -b release/v0.2.0 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.2.0
cd ~/burstguard-v0.2.0
bash scripts/setup_venv.sh          # tạo .venv cô lập trong thư mục này (không cần sudo)
source .venv/bin/activate
burstguard doctor && burstguard smoke
bash scripts/collect_logs.sh        # gom log (thành công hay thất bại) -> reports/bg_report_v0.2.0_*.txt
```

Dữ liệu lớn (Milan, trọng số mô hình) nằm ở `~/burstguard-shared` và dùng chung cho mọi phiên bản.
Chi tiết từng bước, lưới thí nghiệm, phân tích kết quả và cách gửi log: **[docs/README_v0.2.0.md](docs/README_v0.2.0.md)**.

## Cấu trúc mã

```
src/burstguard/
  cli.py            lệnh `burstguard ...`
  config.py         cấu hình mặc định + kiểm tra hợp lệ
  data/             Milan (tải, đọc, chọn site), dữ liệu tổng hợp, cửa sổ
  model.py train.py TTM-R2, 4 chế độ PEFT, huấn luyện cục bộ
  attacks/          trigger burst, client độc hại (poison/scale/constrain/neurotoxin/adaptive)
  defenses/         aggregator bền, SecAgg, LoRA reset, BurstGuard
  fedcore.py        logic client/server dùng chung cho hai engine
  engines/          local (pool tiến trình) và flower (Flower + SecAgg+)
  experiments/      lưới thí nghiệm (shard, tiếp tục) và phân tích thống kê
experiments/E0…E8.toml   các lưới thí nghiệm của bài báo
configs/                 cấu hình nền
scripts/                 setup_venv.sh, collect_logs.sh
```

## Dữ liệu & giấy phép

- Dữ liệu: Barlacchi et al., *A multi-source dataset of urban life in the city of Milan and the Province of Trentino*,
  Scientific Data 2, 150055 (2015) — giấy phép ODbL. Không kèm trong repo; tải bằng `burstguard data download`.
- Mô hình: IBM Granite TinyTimeMixers R2 (`ibm-granite/granite-timeseries-ttm-r2`, Apache-2.0), tải lúc chạy.
- Tấn công trong mã chỉ dùng để đánh giá phòng thủ trong mô phỏng (client giả lập trên dữ liệu công khai).
