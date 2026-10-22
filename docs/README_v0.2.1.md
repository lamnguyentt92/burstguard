# BurstGuard v0.2.1 — Hướng dẫn cài đặt, chạy thí nghiệm cho bài báo và gửi log

> **v0.2.1 = bản sửa lỗi của v0.2.0** (sau log từ vm-e ngày 22/10). Chức năng, cấu hình và lưới thí nghiệm giữ nguyên.
> v0.2 là khung thí nghiệm mô phỏng đầy đủ cho bài báo: tấn công (5 loại), phòng thủ (9 loại + BurstGuard),
> secure aggregation (SecAgg+ thật trong Flower và bản mô phỏng có nhóm), thước đo backdoor, chạy lưới thí nghiệm
> chia cho 5 VM, và phân tích ra bảng/hình/kiểm định thống kê.
> Phần còn thiếu so với bài báo: **triển khai Flower thật trên nhiều VM có mô phỏng mạng (E8 mạng thật)** — để ở v0.3.0.

Chỉ README là tiếng Việt; toàn bộ log, thông báo lỗi và chú thích trong mã là tiếng Anh. Mọi file log/kết quả đều có
số phiên bản trong tên và trong nội dung.

---

## Sửa trong v0.2.1 (so với v0.2.0)

| Lỗi trong log v0.2.0 | Nguyên nhân | Sửa |
|---|---|---|
| `model-check` báo `FileNotFoundError: milan_d1.npz` | lệnh đòi dữ liệu Milan dù chỉ cần mô hình | chạy được khi chưa có dữ liệu (dùng cửa sổ tổng hợp để đo thời gian; số tham số không phụ thuộc dữ liệu) |
| `git=...-dirty`, ~20 file "M" dù không sửa gì | `chmod -R 777 *` ở thư mục home đổi quyền file; git coi là thay đổi | setup đặt `core.fileMode=false` cho checkout; báo cáo/summary bỏ qua thay đổi chỉ về quyền |
| Hàng trăm dòng `DEBUG:...secaggplus_mod.py...` khi chạy Flower | granite-tsfm gọi `logging.basicConfig()` trong từng tiến trình Ray, log DEBUG của Flower lọt ra | tắt ở mọi tiến trình worker (`logutil.quiet_logging`) — còn 0 dòng |
| `WARNING ...get_model.py: Requested prediction_length (36)...` lặp lại | lệnh tắt log cũ trỏ nhầm vào *hàm* `get_model` thay vì module | sửa đúng logger (horizon 36 bước là chủ ý — TTM dùng `prediction_filter_length`) |
| (phát hiện thêm) `setup_venv.sh` hỏng nếu chạy khi `.venv` cũ đang được kích hoạt | script chọn Python của chính `.venv` rồi xoá nó | luôn chọn Python gốc (base interpreter) |

**Không cần** `chmod -R 777`: mọi thứ chạy bằng user hiện tại; 777 làm mọi user trên máy sửa được mã và dữ liệu.

### Nâng cấp từ v0.2.0 (đã cài ở `~/burstguard-v0.2.0`)

```bash
deactivate 2>/dev/null
git clone -b release/v0.2.1 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.2.1
cd ~/burstguard-v0.2.1 && bash scripts/setup_venv.sh && source .venv/bin/activate
burstguard smoke && burstguard model-check -c configs/base.toml
# v0.2.0 chưa có kết quả thí nghiệm (chỉ smoke) -> có thể xoá: rm -rf ~/burstguard-v0.2.0
```

Trọng số TTM-R2 đã tải ở v0.2.0 nằm trong `~/burstguard-shared/hf` nên **không cần** `model-download` lại.

---

## 0. Thay đổi chính của dòng v0.2 so với v0.1.1

| Hạng mục | v0.2.1 |
|---|---|
| Ngôn ngữ log | Tiếng Anh (chỉ README tiếng Việt) |
| Phiên bản trong output | `runs/<thời_gian>_v0.2.1_<lệnh>/`, `results/v0.2.1/<lưới>/`, `reports/bg_report_v0.2.1_*.txt`, `logs/setup_v0.2.1_*.log`, trường `"v": "0.2.1"` trong mọi bản ghi JSONL |
| Cô lập phiên bản | Mỗi phiên bản **một thư mục riêng** + `.venv` riêng có dấu phiên bản; lệnh `burstguard` từ chối chạy nếu `.venv` không khớp phiên bản mã |
| Dữ liệu lớn | Dùng chung giữa các phiên bản tại `~/burstguard-shared` (tải dữ liệu Milan 20,8 GB **một lần**) |
| Engine | `local` (nhanh, xác định, pool tiến trình) và `flower` (Flower Simulation + SecAgg+ thật), dùng **cùng** logic client/server |
| Tấn công | `poison`, `scale`, `constrain_scale`, `neurotoxin`, `adaptive` (mô phỏng client bị chiếm quyền theo các phương pháp đã công bố) |
| Phòng thủ | `fedavg`, `clip_noise`, `krum`, `multikrum`, `trimmed`, `median`, `flame`, `fltrust`, `lora_reset`, **`burstguard`** |
| Secure aggregation | `secagg.enabled`; `secagg.groups>1` = SecAgg theo nhóm (server chỉ thấy tổng của từng nhóm) |
| Thước đo | MASE, MAE, sMAPE + ASR, ASR chặt, TE, AE, UPR, tuổi thọ backdoor L50, TPR/FPR/AUC (ROC) của BurstGuard, chi phí CPU |
| Thí nghiệm | `experiments/E0…E9.toml` (697 job), chạy theo shard trên 5 VM, tự tiếp tục khi bị ngắt |
| Phân tích | `burstguard analyze` → bảng CSV/Markdown/LaTeX, CI bootstrap 95%, Wilcoxon + Holm, hình PNG/PDF |

---

## 1. Cài đặt v0.2.1 song song với phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng:

```bash
git clone -b release/v0.2.1 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.2.1
cd ~/burstguard-v0.2.1
cat VERSION                          # 0.2.1
bash scripts/setup_venv.sh           # tạo ~/burstguard-v0.2.1/.venv (khoảng 3–6 phút)
source .venv/bin/activate
burstguard info                      # in phiên bản, thư mục dự án, thư mục dùng chung
```

Bố cục trên VM sau khi cài:

```
/root/burstguard/            v0.1.1 (giữ nguyên, .venv riêng, không bị đụng tới)
~/burstguard-v0.2.0/         v0.2.0 (nếu còn; xoá được, xem trên)
~/burstguard-v0.2.1/         v0.2.1: .venv/ .tools/ .cache/ runs/ results/v0.2.1/ logs/ reports/
~/burstguard-shared/         DÙNG CHUNG cho mọi phiên bản:
    data/raw/milan/          62 file thô (~20,8 GB) — chỉ cần trên VM làm bước prepare
    data/processed/          milan_d1.npz (~1 MB; "d1" = định dạng dữ liệu 1), synthetic_d1.npz
    hf/                      cache trọng số TTM-R2 (~3 MB)
```

Các cơ chế chống xung đột:

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã v0.2.1 bằng `.venv` của v0.1.1 (hoặc ngược lại) | `.venv/burstguard_version`; `burstguard` báo lỗi và dừng nếu môi trường đang kích hoạt không phải `.venv` của đúng thư mục này hoặc khác phiên bản |
| `git pull` đè mã đang chạy | Mỗi phiên bản một bản clone; nâng cấp = clone thư mục mới |
| Ghi đè kết quả | Kết quả theo phiên bản: `results/v0.2.1/…`; tên run/report có `v0.2.1` |
| Dữ liệu cũ khác định dạng | File đã xử lý mang số định dạng (`milan_d1.npz`); mã kiểm tra số này khi đọc |
| Cụm Ray của hai phiên bản | Engine `flower` luôn khởi tạo cụm Ray cục bộ mới (`address="local"`); engine `local` không dùng Ray |
| Tranh CPU khi chạy hai phiên bản cùng lúc | Mặc định `nice 10`, số worker tự giới hạn theo CPU/RAM; tốt nhất không chạy hai lưới cùng lúc trên một VM |

Chuyển từ v0.1.1: không cần di chuyển gì (v0.1.1 chưa tải dữ liệu thật). Chạy `burstguard model-download` một lần trong
v0.2.1 (3 MB). Muốn đổi vị trí thư mục dùng chung: `export BURSTGUARD_SHARED=/đường/dẫn` **trước** khi cài và mỗi lần chạy.

Gỡ v0.2.1: `rm -rf ~/burstguard-v0.2.1` (không ảnh hưởng v0.1.1 và dữ liệu dùng chung).

---

## 2. Kiểm tra nhanh (mỗi VM)

```bash
cd ~/burstguard-v0.2.1 && source .venv/bin/activate
burstguard doctor            # PASS/WARN/FAIL; FAIL phải sửa
burstguard smoke             # ~1–2 phút: 8 bước gồm cả Flower + SecAgg+ thật
python -m pytest -q          # 15 bài kiểm thử (~1–2 phút)
burstguard model-download    # tải TTM-R2 vào ~/burstguard-shared/hf (bỏ qua nếu đã tải ở bản trước)
burstguard model-check -c configs/base.toml   # số tham số/KiB mỗi cập nhật của 4 chế độ (chưa cần dữ liệu Milan)
```

`smoke` phải kết thúc bằng 8 dòng `[PASS]` và `RUN OK`.

---

## 3. Dữ liệu (làm một lần, rồi chép sang các VM khác)

Trên **một** VM (ví dụ VM1, cần ~25 GB trống trong `~/burstguard-shared`):

```bash
burstguard data download     # 62 file, ~20,8 GB, tiếp tục được nếu bị ngắt, kiểm MD5
burstguard data prepare      # -> ~/burstguard-shared/data/processed/milan_d1.npz
burstguard data info
```

`prepare` in trung bình, độ lệch chuẩn và tỉ lệ 0 của từng site (20 site + 8 khối probe 5×5 ô). Hãy gửi mình đoạn này.

Chép file đã xử lý (~1 MB) sang 4 VM còn lại, **không cần** tải 20 GB trên mỗi VM:

```bash
for h in vm2 vm3 vm4 vm5; do
  ssh $h 'mkdir -p ~/burstguard-shared/data/processed'
  scp ~/burstguard-shared/data/processed/milan_d1.npz $h:~/burstguard-shared/data/processed/
done
```

---

## 4. Chạy một lần (để thử / gỡ lỗi)

```bash
# Thử nhanh bằng TTM-R2 thật trên dữ liệu tổng hợp (không cần Milan):
burstguard data synthetic
burstguard fl -c configs/synthetic_quick.toml

# Một lần chạy trên Milan, ghi đè tham số bằng --set:
burstguard fl -c configs/base.toml --set attack.type=scale --set defense.name=burstguard --set train.peft=lora

# Baseline không liên kết:
burstguard zeroshot -c configs/base.toml
burstguard local    -c configs/base.toml --set train.peft=head
burstguard central  -c configs/base.toml --set train.peft=head

# Kiểm tra engine local khớp Flower (để ghi trong bài):
burstguard equivalence -c configs/base.toml --set fl.rounds=3 --set data.max_train_windows=400
```

Các khoá cấu hình chính (đầy đủ trong `src/burstguard/config.py`):

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `train.peft` | `head` | `head` \| `decoder` \| `lora` \| `full` |
| `engine.name` / `engine.workers` | `local` / 0 | engine; 0 = tự động theo CPU và RAM (~1,4 GB/worker) |
| `attack.type` | `none` | `poison` \| `scale` \| `constrain_scale` \| `neurotoxin` \| `adaptive` |
| `attack.num_malicious` | 2 | số site bị chiếm (trên 20) |
| `attack.start_round` / `end_round` | 1 / 0 | cửa sổ tấn công (0 = đến hết) |
| `trigger.width` / `amplitude` | 3 / 1.0 | burst 30 phút, biên độ × độ lệch chuẩn của site |
| `defense.name` | `fedavg` | xem bảng §0 |
| `secagg.enabled` / `secagg.groups` | false / 1 | secure aggregation; nhóm > 1 = SecAgg theo nhóm |
| `burstguard.reference` | `both` | so với mô hình vừa chấp nhận (`threshold`) và mô hình gốc (`threshold_anchor`) |
| `burstguard.anchor_adaptive` | `true` | ngưỡng anchor bám theo độ trôi lành tính (median + k·MAD); `false` = ngưỡng cố định |
| `burstguard.mode` | `enforce` | `monitor` = chỉ chấm điểm, không loại (dùng để hiệu chỉnh) |

---

## 5. Thí nghiệm cho bài báo

| Lưới | Câu hỏi | Nội dung | Số job | Ước tính thời gian máy* |
|---|---|---|---|---|
| `E0_calibration` | hiệu chỉnh | BurstGuard ở chế độ monitor trên huấn luyện sạch, 4 chế độ PEFT | 12 | ~4 h |
| `E1_clean` | RQ1 | FL × 4 PEFT vs local-only vs centralized vs zero-shot | 39 | ~20 h |
| `E2_attacks` | RQ1/2 | 4 kịch bản (gồm không tấn công) × 4 PEFT, FedAvg | 80 | ~16 h |
| `E3_defenses` | RQ3 | {không tấn công + 3 tấn công} × 9 phòng thủ × {head, lora} | 204 | ~40 h |
| `E4_sensitivity` | RQ3 | số site độc hại {1,2,4} × biên độ trigger {0.5,1,2} × 3 phòng thủ | 81 | ~5 h |
| `E5_lifespan` | RQ2 | tấn công vòng 10–19 / 50 vòng, 4 PEFT × phòng thủ | 39 | ~14 h |
| `E6_adaptive` | RQ3 | tấn công thích nghi, Neurotoxin, trigger ngoài vùng tìm kiếm | 48 | ~10 h |
| `E7_secagg` | RQ3 | SecAgg theo nhóm {1,2,4,5,10} × {fedavg, burstguard, median} | 78 | ~25 h |
| `E8_system` | RQ4 | Flower + SecAgg+ thật: thời gian vòng, chi phí phòng thủ | 8 | ~1 h |
| `E9_ablation` | RQ3 | ablation BurstGuard: 1 tham chiếu, bỏ tối ưu (burst ngẫu nhiên), ít bước/ít probe, vùng tìm kiếm nhỏ, 1 chiều, ngưỡng anchor cố định | 108 | ~11 h |

\* Ước tính sơ bộ cho VM 8 vCPU / 9,7 GB RAM (4 worker), cộng dồn; chia cho 5 VM ⇒ khoảng 1–2 ngày.
**Hãy đo thật**: chạy `--quick` trước, rồi một job thật và gửi mình thời gian để mình chỉnh lại kế hoạch.

### 5.1 Trình tự đề nghị

```bash
# (a) Kiểm tra lưới chạy được, rất nhanh (2 vòng, ít cửa sổ), trên 1 VM:
burstguard grid run experiments/E3_defenses.toml --quick --max-jobs 6
bash scripts/collect_logs.sh --grid E3_defenses

# (b) Hiệu chỉnh ngưỡng BurstGuard (E0), rồi đọc ngưỡng gợi ý:
burstguard grid run experiments/E0_calibration.toml
burstguard calibrate experiments/E0_calibration.toml
#     -> in ra: phân vị điểm sạch, điểm anchor theo vòng (độ trôi), và 3 phương án ngưỡng kèm FPR khi "chạy lại" luật
#        trên dữ liệu E0 (current config / adaptive anchor / fixed anchor; ngưỡng gợi ý = 1,5 × điểm sạch lớn nhất)
#     -> sửa threshold / threshold_anchor / anchor_adaptive trong configs/base.toml theo phương án có FPR = 0
#     -> LÀM TRƯỚC các lưới khác, rồi chép configs/base.toml giống hệt sang cả 5 VM:
#        for h in vm2 vm3 vm4 vm5; do scp configs/base.toml $h:~/burstguard-v0.2.1/configs/; done
#        (analyze sẽ cảnh báo nếu các job trong một lưới chạy với base.toml khác nhau)
#     -> gửi mình: bash scripts/collect_logs.sh --grid E0_calibration

# (c) Các lưới còn lại, chia cho 5 VM (mỗi VM chạy shard của mình, trong tmux):
tmux new -s bg
cd ~/burstguard-v0.2.1
bash scripts/run_grids.sh 1/5        # VM1 dùng 1/5, VM2 dùng 2/5, … VM5 dùng 5/5
#     chạy lần lượt E1, E2, E3, E4, E5, E6, E7, E9 cho shard đó; log: logs/run_grids_v0.2.1_1of5_<thời_gian>.log
#     chỉ một vài lưới:  bash scripts/run_grids.sh 1/5 E3_defenses E7_secagg
#     hoặc từng lưới:    source .venv/bin/activate && burstguard grid run experiments/E3_defenses.toml --shard 1/5

# (d) E8 (đo thời gian) chạy trên MỘT VM khi máy rảnh, để số đo so sánh được:
source .venv/bin/activate && burstguard grid run experiments/E8_system.toml
```

- Bị ngắt (mất SSH, khởi động lại)? Chạy lại **đúng lệnh đó**: job xong bị bỏ qua, job dở được chạy lại.
- Tiến độ: `burstguard grid status experiments/E3_defenses.toml --shards 5`
- Danh sách job: `burstguard grid list experiments/E3_defenses.toml --shard 2/5`

### 5.2 Gom kết quả và phân tích

Mỗi job có thư mục `results/v0.2.1/<lưới>/<job_id>/` (id cố định theo cấu hình), nên chỉ cần chép gộp:

```bash
# trên VM1, kéo kết quả từ 4 VM còn lại:
for h in vm2 vm3 vm4 vm5; do
  rsync -a $h:~/burstguard-v0.2.1/results/v0.2.1/ ~/burstguard-v0.2.1/results/v0.2.1/
done
burstguard analyze experiments/E3_defenses.toml
```

Kết quả trong `results/v0.2.1/E3_defenses/_analysis/`:

| File | Nội dung |
|---|---|
| `summary.md` / `summary.csv` | mỗi cấu hình: MASE, ASR, TE, AE, UPR với CI 95% (bootstrap seed × site), L50, TPR/FPR theo vòng và theo đơn vị sàng lọc, AUC (`auc_units`; `auc_vs_clean` = so với cấu hình sạch tương ứng), tỉ lệ vòng lọt cập nhật độc, CPU |
| `summary.tex` | bảng LaTeX (booktabs) để đưa vào bài |
| `tests.csv` | Wilcoxon ghép cặp theo site so với cấu hình tham chiếu, p hiệu chỉnh Holm |
| `figures/*.png, *.pdf` | ASR/MASE theo phòng thủ, ASR theo vòng (tuổi thọ), `burstguard_roc` (đường ROC) |

---

## 6. Gửi log để mình phân tích và sửa

```bash
bash scripts/collect_logs.sh                 # lần chạy gần nhất
bash scripts/collect_logs.sh --last 5        # 5 lần gần nhất
bash scripts/collect_logs.sh --failed        # mọi lần chạy lỗi
bash scripts/collect_logs.sh --setup         # khi cài đặt lỗi (không cần .venv)
bash scripts/collect_logs.sh --grid E3_defenses   # tiến độ lưới + traceback job lỗi + bảng phân tích
```

Tạo `reports/bg_report_v0.2.1_<host>_<thời_gian>.txt` (gửi file này) và `.tar.gz` (chỉ khi mình yêu cầu).
Với `--grid`, file `.tar.gz` còn chứa `_analysis/` và kết quả gọn của từng job (`result.json` + các dòng đánh giá) —
**gửi cả `.tar.gz` sau khi `burstguard analyze`** để mình chạy lại phân tích, vẽ hình và viết phần Results. Báo cáo có
phiên bản, commit, danh sách file bị sửa trong checkout, các checkout khác trên máy, trạng thái dữ liệu dùng chung, lỗi
và đoạn cuối log. Khi lỗi, `summary.json` có thêm trường `hint` gợi ý cách sửa.

---

## 7. Thiết kế (tóm tắt để viết phần Method)

- **Site / dữ liệu:** 20 site = khối 5×5 ô lưới Milan (trải từ trung tâm ra ngoại vi), chuỗi hoạt động Internet 10 phút;
  8 khối probe không thuộc site nào làm **dữ liệu công khai của server** (dùng cho BurstGuard và FLTrust).
  Chia: train 1/11–7/12, val 8/12–14/12, test 15/12–24/12, holiday 25/12–1/1.
- **Mô hình:** TTM-R2 `512-48-ft-r2.1` (ngữ cảnh 512, dự báo 36 bước = 6 giờ), 4 chế độ: head, decoder,
  LoRA r=8 trên fc1/fc2 + head, full. Số tham số huấn luyện và KiB/cập nhật của từng chế độ trên trọng số thật:
  `burstguard model-check -c configs/base.toml` (gửi mình kết quả để đưa vào bảng của bài).
- **Mô phỏng client bị chiếm quyền:** trigger = burst không âm, biên độ a·σ_site ở w khe cuối ngữ cảnh; nhãn đích ρ·y (ρ=0,3).
  `scale` khuếch đại cập nhật n/m (model replacement); `constrain_scale` chiếu về chuẩn của cập nhật lành;
  `neurotoxin` chỉ cập nhật các toạ độ ít thay đổi; `adaptive` thêm burst ngẫu nhiên với nhãn sạch (decoy).
- **BurstGuard:** chấm điểm mô hình **tổng hợp** (nên dùng được với SecAgg): tìm burst xấu nhất trong vùng
  {δ ≥ 0, w ≤ 6 khe cuối, ≤ 2σ} bằng projected sign-gradient ascent trên cửa sổ probe, đo độ thay đổi tương đối của dự báo
  so với (i) mô hình vừa chấp nhận và (ii) mô hình gốc. Loại vòng (hoặc loại nhóm khi SecAgg theo nhóm) nếu vượt ngưỡng.
- **SecAgg:** engine `flower` dùng giao thức SecAgg+ thật; engine `local` mô phỏng đúng phép cắt ±8 và lượng tử hoá ngẫu nhiên
  2²² mức của Flower. `burstguard equivalence` đối chiếu hai engine.

Kiểm thử nội bộ v0.2.0–v0.2.1 (dữ liệu tổng hợp, TTM khởi tạo ngẫu nhiên, decoder, 20 site, 8 vòng, 2 vCPU) — chỉ để kiểm tra
pipeline, **không** phải số liệu cho bài (số liệu bài phải lấy từ TTM-R2 + Milan):

| Lần chạy | MASE test | ASR test | BurstGuard |
|---|---|---|---|
| Sạch + BurstGuard | 0,813 | 0,000 | 0/8 vòng bị loại (điểm last ≤ 0,071 < 0,15; điểm anchor trôi 0,04 → 0,38) |
| `scale` (2 site độc hại) + SecAgg 5 nhóm + BurstGuard | 0,811 | 0,000 | gắn cờ đúng 16/16 nhóm có site độc hại, 0/24 nhóm lành (AUC 1,0); điểm nhóm độc 8,8–77 |
| `scale` (2 site độc hại) + FedAvg, không phòng thủ | 1,379 | 0,379 | — (ASR val tăng 0,008 → 0,383 qua 8 vòng) |

Điểm anchor tăng đều theo vòng trên huấn luyện lành tính → v0.2.1 dùng ngưỡng anchor thích nghi (`anchor_adaptive`).
Chi phí sàng lọc: ~21 s CPU/vòng cho 1 đơn vị, ~113 s cho 5 nhóm trên 2 vCPU; trên VM 8 vCPU BurstGuard dùng tối đa 4 luồng
khi client đang rảnh (`burstguard.threads`).

---

## 8. Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `ERROR (burstguard v0.2.1): the active virtual environment ... does not belong to this checkout` | `deactivate; cd ~/burstguard-v0.2.1 && source .venv/bin/activate` |
| `.venv was built for v0.1.1 but the code is v0.2.1` | `bash scripts/setup_venv.sh --recreate` |
| `dataset not found ... milan_d1.npz` | §3 (tải + prepare, hoặc chép file từ VM khác) |
| Job lỗi `BrokenProcessPool` / bị kill | Thiếu RAM: `--set engine.workers=2` hoặc sửa `engine.workers` trong `configs/base.toml` |
| BurstGuard loại cả vòng sạch | Ngưỡng thấp so với dữ liệu thật: chạy E0 + `burstguard calibrate`, cập nhật ngưỡng |
| Flower in cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 |
