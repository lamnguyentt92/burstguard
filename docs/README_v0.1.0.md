# BurstGuard v0.1.0 — Hướng dẫn cài đặt, chạy và gửi log

> **Phạm vi v0.1.0 ("nền móng"):** môi trường ảo cô lập, pipeline dữ liệu Milan, nạp TTM-R2, baseline
> (seasonal-naive, zero-shot), **học liên kết SẠCH** (FedAvg, 4 chế độ fine-tune: head / decoder / lora / full)
> trên Flower Simulation, và bộ công cụ gom log. **Chưa có** tấn công/phòng thủ — phần đó ở v0.2.0, sau khi
> v0.1.0 chạy được trên VM của bạn.

---

## 0. Đã kiểm thử những gì (và chưa)

| Hạng mục | Trạng thái |
|---|---|
| `setup_venv.sh` từ bản clone sạch trên Ubuntu 24.04 với **Python 3.11 và 3.12** (kể cả nhánh dự phòng tải torch từ PyPI) | ✅ chạy thật |
| Wheel của mọi thư viện đã ghim có sẵn cho Python 3.13 | ✅ kiểm tra (chưa cài thử đầy đủ) |
| `pytest` (5 bài: cấu hình, cắt cửa sổ, đọc file Milan giả lập .txt/.gz/có header, mô hình & PEFT) | ✅ |
| `burstguard smoke` (dữ liệu tổng hợp + TTM khởi tạo ngẫu nhiên, FL head & lora) | ✅ ~35 giây / 2 vCPU |
| `run_e1.sh --quick` trên dữ liệu tổng hợp 20 site, 4 chế độ | ✅ ~5 phút / 2 vCPU |
| Đọc file Milan cỡ thật (giả lập 2 ngày × 10.000 ô, ~100 MB/file) | ✅ ~1 giây/file |
| **Tải trọng số TTM-R2 thật từ Hugging Face** | ⚠️ *chưa chạy được* (máy kiểm thử bị chặn huggingface.co) |
| **Tải dữ liệu từ Harvard Dataverse** | ⚠️ *chưa chạy được* (máy kiểm thử bị chặn Dataverse) |

Hai mục ⚠️ là việc **đầu tiên** cần bạn chạy trên VM (§4.3, §4.4). Nếu lỗi, gửi log cho mình (§6).

---

## 1. Yêu cầu

| | Tối thiểu | Khuyến nghị |
|---|---|---|
| Hệ điều hành | Linux x86_64 (Ubuntu 22.04 / 24.04 đã tính tới) | Ubuntu 24.04 |
| Python | 3.11 – 3.13 (nếu máy chỉ có 3.10, script tự tải Python 3.12 riêng cho dự án) | 3.12 |
| CPU | 2 vCPU | ≥ 8 vCPU (mỗi client song song dùng 1 vCPU) |
| RAM | 6 GB | ≥ 16 GB (mỗi worker Ray ~1,3–1,4 GB) |
| Đĩa trống | 15 GB (môi trường ảo ~3–5 GB) | + dung lượng dữ liệu Milan thô (xem bằng `--dry-run`, §4.4) |
| Mạng ra ngoài | PyPI, GitHub | + huggingface.co, download.pytorch.org, dataverse.harvard.edu |
| Quyền | **không cần sudo** | |

Gói hệ thống cần có sẵn: `git`, `bash`, `curl` (hoặc `wget`), `tar`. Nếu `python3 -m venv` báo thiếu
`ensurepip` trên Ubuntu và bạn *không muốn* cài `python3.X-venv`, script sẽ tự dùng `uv` để tải Python riêng.

---

## 2. Lấy mã nguồn

```bash
git clone https://github.com/lamnguyentt92/burstguard.git
cd burstguard
git checkout v0.1.0          # đúng phiên bản của tài liệu này
cat VERSION                  # phải in 0.1.0
```

Cập nhật về sau: `git fetch --tags && git checkout v0.2.0` (khi có).

---

## 3. Cài đặt môi trường ảo (cô lập hoàn toàn)

```bash
bash scripts/setup_venv.sh
```

Script làm 5 bước, in rõ từng bước và ghi nhật ký vào `logs/setup_<thời_gian>.log`:

1. Tìm Python 3.11–3.13 (thứ tự: `$BG_PYTHON`, `python3.12`, `python3.11`, `python3.13`, `python3`). Không có → cài `uv` cục bộ
   vào `.tools/uv/` và tải Python 3.12 vào `.tools/python/` (**không** sửa `PATH`, **không** ghi vào `~/.local/bin`).
2. Tạo `.venv/` trong thư mục dự án.
3. Cài `torch==2.11.0` **bản CPU** từ `download.pytorch.org` (~200 MB). Nếu bị chặn → tự chuyển sang PyPI (bản kèm CUDA,
   vài GB, vẫn chạy trên CPU) và in cảnh báo.
4. Cài thư viện đã ghim phiên bản (`requirements.txt`) và dự án ở chế độ editable.
5. Chạy `burstguard doctor --no-net`.

Kết thúc thành công sẽ in `CÀI ĐẶT XONG` và ghi `status=success` vào `logs/setup_<thời_gian>.status`.

Tuỳ chọn:

```bash
bash scripts/setup_venv.sh --recreate          # xoá .venv rồi cài lại từ đầu
BG_PYTHON=/usr/bin/python3.11 bash scripts/setup_venv.sh   # chỉ định Python cụ thể
```

### Vì sao không ảnh hưởng dịch vụ khác

| Cơ chế | Chi tiết |
|---|---|
| Môi trường ảo riêng | Mọi thư viện nằm trong `.venv/` của dự án; không dùng `sudo pip`, không đụng Python hệ thống |
| Cache trong dự án | `HF_HOME`, `TORCH_HOME`, cache pip/uv → `.cache/` (không ghi vào `~/.cache`) |
| Bắt buộc chạy trong venv | Lệnh `burstguard` từ chối chạy nếu chưa `source .venv/bin/activate` |
| Hạ độ ưu tiên CPU | Mặc định `nice 10` cho tiến trình và mọi worker Ray (đổi bằng `burstguard --nice 0 ...`) |
| Giới hạn tài nguyên Ray | `sim.num_cpus = 0` (tự động) = min(số CPU − 1, số worker vừa RAM trống − 2,5 GB); luôn chừa ≥ 1 CPU |
| Luồng BLAS | Mỗi tiến trình 1 luồng (`OMP_NUM_THREADS=1`), tránh chiếm hết CPU |
| Mạng | Ray chạy cụm cục bộ, không có dashboard; nó mở vài cổng TCP ngẫu nhiên trên VM trong lúc chạy — nếu VM có IP công khai, giữ tường lửa mặc định chặn kết nối vào |

Gỡ bỏ hoàn toàn: `rm -rf .venv .tools .cache runs logs reports` (dữ liệu nằm ở `data/`).

---

## 4. Chạy

Luôn kích hoạt môi trường ảo trước (mỗi phiên terminal mới):

```bash
cd burstguard
source .venv/bin/activate
burstguard --version         # burstguard 0.1.0
```

> Chạy dài trên VM qua SSH: dùng `tmux` hoặc `screen` (hoặc `nohup ... &`) để không bị ngắt khi mất kết nối.

### 4.1 Kiểm tra môi trường

```bash
burstguard doctor            # gồm kiểm tra mạng tới pypi / huggingface / pytorch / dataverse / github
```
In `[PASS]/[WARN]/[FAIL]` từng mục. `FAIL` = phải sửa; `WARN` = chạy được nhưng nên xem.

### 4.2 Kiểm thử đầu-cuối không cần mạng (≈ 1 phút)

```bash
burstguard smoke             # dữ liệu tổng hợp + TTM ngẫu nhiên + FL 2 vòng × 4 site (head & lora)
python -m pytest             # 5 bài kiểm thử đơn vị (~10 giây)
```
Cuối `smoke` phải có 5 dòng `[PASS]` và `RUN OK`.

### 4.3 Mô hình TTM-R2 thật (**cần chạy và gửi kết quả cho mình**)

```bash
burstguard model-download    # tải trọng số vào .cache/huggingface rồi thử nạp offline
burstguard data synthetic    # dữ liệu tổng hợp 20 site (để model-check có dữ liệu)
burstguard model-check -c configs/e0_synthetic_head.toml
```

`model-check` in cho từng chế độ: số tham số train được, KiB/cập nhật, thời gian CPU / 512 cửa sổ, và **sai lệch head cache**
(phải ≈ 0; nếu > 1e-3 chương trình tự tắt cache và chạy chậm hơn — báo cho mình).

Biến thể mặc định do `get_model` chọn cho ngữ cảnh 512 / dự báo 36 bước là **`512-48-ft-r2.1`** (có freq-prefix, cần token tần
suất "10min" — đã xử lý trong mã). Muốn dùng bản không freq-prefix: `--set model.revision=main` (512-96-r2, cắt còn 36 bước).

Không có mạng tới huggingface.co trên VM? Chạy `burstguard model-download` trên máy khác (cùng phiên bản mã), rồi chép
thư mục `.cache/huggingface/` sang VM vào đúng vị trí trong dự án.

### 4.4 Dữ liệu Milan thật (**cần chạy và gửi kết quả cho mình**)

```bash
burstguard data download --dry-run   # chỉ liệt kê file + tổng dung lượng, chưa tải
burstguard data download             # tải về data/raw/milan/ (tiếp tục được nếu bị ngắt; kiểm MD5)
burstguard data prepare              # -> data/processed/milan.npz (20 site + 8 probe, khối 5×5 ô)
burstguard data info                 # mô tả file đã xử lý
```

- Lệnh `download` hỏi cả hai DOI "Telecommunications activity" của Barlacchi et al. (2015) và chỉ giữ file `sms-call-internet-mi-*`.
  Tải một khoảng ngày: `--from 2013-11-01 --to 2013-11-07`.
- Không truy cập được Dataverse từ VM: tải thủ công trên trình duyệt (tìm "Telecommunications - SMS, Call, Internet - MI" trên
  dataverse.harvard.edu), chép các file `sms-call-internet-mi-YYYY-MM-DD.txt` (hoặc `.gz`/`.zip`) vào `data/raw/milan/`
  rồi chạy `burstguard data prepare`.
- `prepare` in trung bình / độ lệch chuẩn / tỉ lệ 0 của từng site — gửi mình phần này để kiểm tra cách chọn site.
- Giấy phép dữ liệu: **ODbL** — ghi nguồn khi công bố; dữ liệu đã xử lý nếu chia sẻ cũng phải theo ODbL.

### 4.5 Baseline và học liên kết sạch (E1)

```bash
burstguard zeroshot -c configs/e1_clean_head.toml    # seasonal-naive + TTM zero-shot trên val/test/holiday
burstguard fl -c configs/e1_clean_head.toml          # FedAvg 30 vòng, head-only
burstguard fl -c configs/e1_clean_lora.toml --seed 1 # chế độ LoRA, seed 1
burstguard local -c configs/e1_clean_head.toml       # baseline: mỗi site fine-tune riêng
```

Hoặc chạy trọn bộ E1 (model-check → zeroshot → FL × 4 chế độ) rồi tự gom log:

```bash
bash scripts/run_e1.sh --quick       # 3 vòng, ít cửa sổ — kiểm tra nhanh trước (~10–30 phút tuỳ VM)
bash scripts/run_e1.sh               # đầy đủ 30 vòng
```

Ghi đè bất kỳ tham số nào bằng `--set khoá=giá_trị` (lặp được), ví dụ:

```bash
burstguard fl -c configs/e1_clean_head.toml --set fl.rounds=10 --set sim.num_cpus=4 --set data.num_sites=10
```

Các khoá quan trọng (đầy đủ trong `src/burstguard/config.py`):

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `data.path` | `data/processed/milan.npz` | file dữ liệu đã xử lý |
| `data.num_sites` | 20 | số site (= số client FL) |
| `data.context` / `data.horizon` | 512 / 36 | ngữ cảnh (≈3,6 ngày) / dự báo 6 giờ |
| `model.source` | `hf` | `hf` (Hugging Face), `local` (thư mục), `random` (thử pipeline) |
| `train.peft` | `head` | `head` \| `decoder` \| `lora` \| `full` |
| `fl.rounds` / `fl.eval_every` | 30 / 5 | số vòng / đánh giá mỗi N vòng (luôn đánh giá test + holiday ở vòng cuối) |
| `sim.num_cpus` | 0 (tự động) | CPU giao cho Ray = số client song song (với `cpus_per_client=1`) |

---

## 5. Kết quả nằm ở đâu

Mỗi lệnh tạo một thư mục `runs/<thời_gian>_<lệnh>_<tên>/`; đường dẫn lần chạy gần nhất ghi trong `runs/LATEST`.

| File | Nội dung |
|---|---|
| `command.txt` | lệnh đã chạy |
| `config.toml` | cấu hình **đã hợp nhất** (mặc định + file + `--set`) — tái lập được |
| `env.json` | máy, Python, CPU, RAM, git commit |
| `console.log` | toàn bộ output (kể cả log của worker Ray và Flower) |
| `summary.json` | `status` = `success` / `failed` / `interrupted`, thời gian, chỉ số chính, `hint` khi lỗi |
| `error.txt` | traceback đầy đủ (chỉ khi lỗi) |
| `metrics.jsonl` | (FL) mỗi vòng: loss, KiB/cập nhật, thời gian vòng; mỗi lần đánh giá: MASE/MAE từng site |
| `fl_result.json`, `zeroshot.json`, `model_check.json`, `doctor.json`, `dataset_info.json` | kết quả theo lệnh |

Chỉ số chính: **MASE (ngày)** = MAE mô hình / MAE của dự báo "giống hệt cùng giờ hôm qua". < 1 nghĩa là tốt hơn baseline mùa vụ.

---

## 6. Gửi output để mình phân tích và sửa

### Khi lệnh **thành công** hoặc **thất bại** (dùng chung)

```bash
bash scripts/collect_logs.sh               # lần chạy gần nhất + trạng thái cài đặt
bash scripts/collect_logs.sh --last 6      # 6 lần chạy gần nhất (vd. sau run_e1.sh)
bash scripts/collect_logs.sh --failed      # mọi lần chạy không thành công
bash scripts/collect_logs.sh --run runs/<thư_mục>
```

### Khi **cài đặt** thất bại (chưa có .venv cũng chạy được)

```bash
bash scripts/collect_logs.sh --setup
```

Script tạo:

- `reports/bg_report_<host>_<thời_gian>.txt` — **dán nội dung hoặc đính kèm file này cho mình**. Gồm: phiên bản + git commit,
  phần cứng, phiên bản thư viện, trạng thái cài đặt, với mỗi lần chạy: lệnh, `summary.json`, traceback (15 dòng đầu + 70 dòng
  cuối), các dòng nghi lỗi và đoạn cuối `console.log`, đuôi `metrics.jsonl`, và lỗi worker Ray nếu có.
  Lần chạy thành công được rút gọn (25 dòng cuối) để báo cáo ngắn.
- `reports/bg_report_<host>_<thời_gian>.tar.gz` — bản đầy đủ (thư mục run, log cài đặt, `pip freeze`, log Ray). Chỉ cần gửi khi mình yêu cầu.

Không có thông tin nhạy cảm nào ngoài hostname, tên user và đường dẫn thư mục; xem nhanh file `.txt` trước khi gửi nếu cần.

### Trình tự đề nghị cho lần thử đầu tiên trên VM

```bash
bash scripts/setup_venv.sh            || bash scripts/collect_logs.sh --setup
source .venv/bin/activate
burstguard doctor
burstguard smoke
burstguard model-download
burstguard data synthetic && burstguard model-check -c configs/e0_synthetic_head.toml
burstguard data download --dry-run
bash scripts/collect_logs.sh --last 5   # gửi mình file reports/bg_report_*.txt
```

Sau đó (nếu ổn): `burstguard data download && burstguard data prepare && bash scripts/run_e1.sh --quick`, rồi
`bash scripts/collect_logs.sh --last 6`.

---

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `LỖI: burstguard phải chạy trong môi trường ảo` | `source .venv/bin/activate` |
| Không tìm thấy Python 3.11+ và không tải được uv | `sudo apt install python3.12 python3.12-venv` (nếu được phép) hoặc đặt `BG_PYTHON=/đường/dẫn/python3.11` |
| Cảnh báo tải torch từ PyPI (bản CUDA, nặng) | Bình thường khi `download.pytorch.org` bị chặn; chỉ tốn đĩa |
| `Không tải được mô hình từ Hugging Face` | §4.3: chép `.cache/huggingface` từ máy khác, hoặc `--set model.source=random` để thử pipeline |
| `Chưa có dữ liệu đã xử lý` | `burstguard data synthetic` (thử) hoặc `data download` + `data prepare` |
| Không có `summary.json`, log dừng đột ngột | Có thể hết RAM (OOM). Giảm `--set sim.num_cpus=2` hoặc `--set data.num_sites=10`; gửi log |
| `N client lỗi ở vòng ...` | Xem dòng `[client N] LỖI trong fit` trong `console.log`; gửi log |
| Cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 — chế độ triển khai thật trên nhiều VM sẽ có ở bản sau |

---

## 8. Cấu trúc mã (v0.1.0)

```
scripts/setup_venv.sh     cài đặt môi trường ảo cô lập
scripts/collect_logs.sh   gom log thành công/thất bại
scripts/run_e1.sh         chạy trọn bộ E1
configs/                  e0_synthetic_head.toml, e1_clean_{head,decoder,lora,full}.toml
src/burstguard/
  cli.py                  lệnh burstguard (doctor, data, model-download, model-check, zeroshot, local, fl, smoke)
  runctx.py               thư mục runs/, ghi log mức file-descriptor, summary.json, error.txt
  config.py               cấu hình mặc định + TOML + --set
  doctor.py, hints.py     kiểm tra môi trường; gợi ý khắc phục theo loại lỗi
  data/                   dataverse.py (tải), milan.py (đọc + chọn site), synthetic.py, store.py (.npz), windows.py
  model.py                nạp TTM, 4 chế độ fine-tune, trao đổi tham số, head-only có cache
  train.py, metrics.py    vòng huấn luyện cục bộ; MAE / MASE / sMAPE
  sitedata.py, baselines.py  cửa sổ theo site, đánh giá; seasonal-naive, zero-shot, cục bộ
  fl/                     client.py, server.py (FedAvg lối legacy — tương thích SecAgg+ cho v0.2), sim.py
tests/test_core.py
```
