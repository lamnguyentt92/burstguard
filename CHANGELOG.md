# Lịch sử thay đổi

Đánh số theo [Semantic Versioning](https://semver.org/lang/vi/): `MAJOR.MINOR.PATCH`. Mỗi phiên bản có nhánh `release/vX.Y.Z`
trên GitHub và hướng dẫn riêng `docs/README_vX.Y.Z.md`. Bản sửa lỗi sau khi bạn gửi log sẽ tăng số PATCH (v0.1.1, v0.1.2, …).

## [0.1.1] — 2026-10-21

### Sửa
- Tắt telemetry mặc định của Flower (`FLWR_TELEMETRY_ENABLED=0`) — v0.1.0 gửi thống kê sử dụng tới telemetry.flower.ai.
- Hướng dẫn checkout theo nhánh `release/vX.Y.Z` (tag không đẩy được từ phiên phát triển).
- Không đổi thư viện/cấu hình: không cần cài lại `.venv`.

## [0.1.0] — 2026-10-21

### Thêm
- `scripts/setup_venv.sh`: tạo `.venv` cô lập trong dự án; tự tìm Python 3.11–3.13 hoặc tải Python 3.12 riêng qua `uv`
  (không sửa PATH, không cần sudo); torch 2.11.0 bản CPU (tự chuyển sang PyPI nếu bị chặn); ghi `logs/setup_*.log/.status`.
- `scripts/collect_logs.sh`: gom log thành công/thất bại thành `reports/bg_report_*.txt` + `.tar.gz` (chạy được cả khi `.venv` hỏng).
- `scripts/run_e1.sh`: chạy trọn bộ E1 (model-check → zeroshot → FL head/decoder/lora/full), chế độ `--quick`.
- Lệnh `burstguard`: `doctor`, `smoke`, `data synthetic|download|prepare|info`, `model-download`, `model-check`, `zeroshot`, `local`, `fl`.
- Mỗi lần chạy có thư mục `runs/<id>/` với `console.log` (bắt ở mức file-descriptor, gồm log worker Ray), `summary.json`
  (status + gợi ý khắc phục), `error.txt`, `metrics.jsonl`, `config.toml` đã hợp nhất.
- Dữ liệu: tải Milan từ Harvard Dataverse (tiếp tục tải dở, kiểm MD5), đọc file `.txt/.gz/.zip` có/không header,
  chọn 20 site + 8 probe (khối 5×5 ô, từ trung tâm ra ngoại vi), split train/val/test/holiday theo ngày; dữ liệu tổng hợp để thử.
- Mô hình: nạp TTM-R2 qua `get_model` (biến thể `512-48-ft-r2.1`, xử lý token tần suất 10 phút), 4 chế độ fine-tune
  (head, decoder, LoRA r=8 trên fc1/fc2, full); head-only có cache đầu ra decoder (tự kiểm tra khớp với forward đầy đủ).
- FL: FedAvg lối legacy của Flower 1.41 (để v0.2 bật được SecAgg+), đánh giá tập trung MASE/MAE/sMAPE theo site, đo KiB/cập nhật
  và thời gian vòng; client lỗi làm dừng lần chạy (`fl.strict=true`) thay vì bị nuốt im lặng.
- Cô lập tài nguyên: bắt buộc chạy trong venv, `nice 10`, cache trong `.cache/`, Ray tự giới hạn theo CPU và RAM trống.
- `tests/test_core.py`: 5 bài kiểm thử đơn vị.

### Đã biết / chưa kiểm thử
- Chưa chạy với trọng số TTM-R2 thật và chưa tải thật từ Dataverse (máy kiểm thử bị chặn hai địa chỉ này).
- `run_simulation` của Flower 1.41 in cảnh báo "deprecated" — vẫn hoạt động; chế độ triển khai thật nhiều VM để bản sau.
