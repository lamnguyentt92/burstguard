# BurstGuard v0.3.8 — Sửa BurstGuard cho lưu lượng SMS và cuộc gọi (X4, X5)

> **v0.3.8 = v0.3.7 + "sàn" cho điểm thay đổi tương đối (`burstguard.rel_floor`) + hiệu chỉnh ngưỡng theo từng loại
> lưu lượng (`calibrate --write-thresholds`, `burstguard.threshold_file`) + lệnh kiểm tra `burstguard bg-check` +
> 2 lưới X4 (monitor, hiệu chỉnh) và X5 (enforce với ngưỡng đã hiệu chỉnh).**
> Mặc định không đổi: `rel_floor = 0`, nên mọi kết quả của v0.3.5–v0.3.7 vẫn giữ nguyên giá trị.
> `EXPERIMENT_CODE` vẫn là 0.3.5. v0.3.7 (X3) cứ chạy tiếp; X4 tự xếp hàng sau X3 trên từng máy.

Chỉ README là tiếng Việt; log, thông báo lỗi và chú thích trong mã là tiếng Anh; mọi log/kết quả có `v0.3.8` trong tên.

---

## 1. Vấn đề tìm thấy ở v0.3.6 (X2)

Trên SMS và cuộc gọi, BurstGuard dùng ngưỡng của Internet (0,08 / 0,3) đã **gắn cờ mọi vòng, kể cả vòng sạch**
(FPR = 1,0). Mô hình vì thế không bao giờ được cập nhật và MASE đứng yên ở mức zero-shot (cuộc gọi 0,643, SMS 0,710).

Nguyên nhân: điểm của BurstGuard là *mức thay đổi tương đối* của dự báo, tức chia cho |f(x)|. Ban đêm số cuộc gọi
và SMS gần 0, nên phép chia làm điểm vọt lên. Điểm của vòng sạch là 1–160 trên SMS/cuộc gọi, trong khi trên Internet
chỉ ≤ 0,05.

Cách sửa gồm hai phần (đây cũng là cách làm chuẩn với bộ phát hiện bất thường):
1. **Đặt sàn:** chia cho max(|f(x)|, 0,1·σ) thay vì |f(x)|. Trên Internet, dự báo không bao giờ gần 0, nên sàn
   không có tác dụng gì. Lệnh `bg-check` dùng để xác nhận điều này trên chính các mô hình đã lưu của v0.3.5.
2. **Hiệu chỉnh ngưỡng cho từng loại lưu lượng** bằng các vòng sạch, như E0 đã làm cho Internet:
   - X4: chạy ở chế độ monitor, ghi điểm của mọi vòng, sạch lẫn bị tấn công;
   - `calibrate --write-thresholds`: ghi ngưỡng ra file;
   - X5: chạy ở chế độ enforce với ngưỡng vừa ghi.

| Lưới | Nội dung | Job |
|---|---|---|
| `X4_traffic_bg_monitor` | SMS/cuộc gọi × {head 2 seed, LoRA 1 seed} × {không, γ=10, γ=3}; monitor, `rel_floor = 0,1` | 18 |
| `X5_traffic_bg_enforce` | như X4 nhưng enforce (regroup), ngưỡng lấy từ `shared:bg_thresholds.toml` | 18 |

Ước tính X4 khoảng 1–1,5 giờ, X5 khoảng 1,5–2 giờ trên 5 máy.

## 2. Lệnh chạy — tất cả trên vm-e

### Bước 1 — cài và kiểm thử v0.3.8 (~10 phút; X3 vẫn chạy)

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.8 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.8
cd ~/burstguard-v0.3.8 && bash scripts/setup_venv.sh && source .venv/bin/activate
nice -n 10 python -m pytest -q        # 30 passed
nice -n 10 burstguard smoke           # 8 dòng [PASS], RUN OK
```

### Bước 2 — kiểm tra sàn không làm đổi kết quả Internet (~2–5 phút)

```bash
nice -n 10 burstguard bg-check --results ~/burstguard-v0.3.5/results/v0.3.5 2>&1 | tee logs/bg_check.out
```

Dòng cuối phải là `=> internet models: largest change ... (identical)`. Các dòng `sms` và `call` cho biết sàn có tác
dụng ở bao nhiêu phần trăm dự báo. Gửi mình file `logs/bg_check.out`.

### Bước 3 — cài trên 4 VM còn lại và xếp X4 sau X3

```bash
bash scripts/cluster.sh install && bash scripts/cluster.sh smoke
bash scripts/cluster.sh start "--wait-idle --tier traffic_bg"
bash scripts/cluster.sh status        # RUNNING (đang chờ v0.3.7 hoặc đang chạy X4)
```

### Bước 4 — khi X4 xong (`cluster.sh status` của v0.3.8: cả 5 máy `not running` + `ALL GRIDS OK`)

Hiệu chỉnh ngưỡng cho từng loại lưu lượng, chép sang các máy, rồi chạy X5:

```bash
bash scripts/sync_results.sh
burstguard calibrate experiments/X4_traffic_bg_monitor.toml --where data.path=shared:data/processed/milan_sms_d1.npz --write-thresholds shared:bg_thresholds.toml
burstguard calibrate experiments/X4_traffic_bg_monitor.toml --where data.path=shared:data/processed/milan_call_d1.npz --write-thresholds shared:bg_thresholds.toml
cat ~/burstguard-shared/bg_thresholds.toml          # 2 mục: sms và call
bash scripts/cluster.sh push-data                   # chép bg_thresholds.toml sang 4 VM
bash scripts/cluster.sh start "--tier traffic_bg2"
```

Nếu `bg_thresholds.toml` thiếu trên máy nào, job X5 trên máy đó báo lỗi rõ ràng: chạy lại `push-data` rồi `start`.

### Bước 5 — khi X5 xong: gộp tất cả và xuất bảng/hình cho bài

```bash
cd ~/burstguard-v0.3.8 && source .venv/bin/activate
bash scripts/cluster.sh import 0.3.5
bash scripts/cluster.sh import 0.3.6
bash scripts/cluster.sh import 0.3.7
bash scripts/cluster.sh --bg collect E0_calibration E1_clean E2_attacks E3_defenses E7_secagg E9_ablation E4_sensitivity E5_lifespan E6_adaptive E8_system X1_traffic_clean X2_traffic_defenses X3_trigger_offset X4_traffic_bg_monitor X5_traffic_bg_enforce
tail -f $(ls -t logs/cluster_collect_*.log | head -1)     # chờ DONE
burstguard paper && bash scripts/collect_logs.sh --campaign
ls -t reports/ | head -2                                   # gửi mình .txt và .tar.gz
```

## 3. Nếu có lỗi

| Bước | Gửi mình |
|---|---|
| 1 (setup / pytest / smoke) | toàn bộ màn hình lỗi + `bash scripts/collect_logs.sh --setup` (hoặc `--last 3`) |
| 2 (bg-check) | `logs/bg_check.out` |
| 3–4 (install / start / calibrate / push-data) | màn hình lỗi + các file `logs/cluster_<lệnh>_<VM>_*.log` |
| 5 (job lỗi, import, collect) | màn hình lỗi + `bash scripts/sync_results.sh && bash scripts/collect_logs.sh --grid X5_traffic_bg_enforce` |

---

# Phần tham khảo

## A. Cài đặt v0.3.8 song song với phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng:

```bash
git clone -b release/v0.3.8 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.8
cd ~/burstguard-v0.3.8
cat VERSION                          # 0.3.8
bash scripts/setup_venv.sh           # tạo ~/burstguard-v0.3.8/.venv (khoảng 3–6 phút)
source .venv/bin/activate
burstguard info                      # in phiên bản, thư mục dự án, thư mục dùng chung
```

Bố cục trên VM sau khi cài:

```
/root/burstguard/            v0.1.1 (giữ nguyên, .venv riêng, không bị đụng tới)
~/burstguard-v0.2.2/         v0.2.2 (xoá được sau khi cài v0.3.8)
~/burstguard-v0.3.8/         v0.3.8: .venv/ .tools/ .cache/ runs/ results/v0.3.8/ logs/ reports/
~/burstguard-shared/         DÙNG CHUNG cho mọi phiên bản:
    data/raw/milan/          62 file thô (~20,8 GB) — chỉ cần trên VM làm bước prepare
    data/processed/          milan_d1.npz (~1 MB; "d1" = định dạng dữ liệu 1), synthetic_d1.npz
    hf/                      cache trọng số TTM-R2 (~3 MB)
```

Các cơ chế chống xung đột:

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã v0.3.8 bằng `.venv` của v0.1.1 (hoặc ngược lại) | `.venv/burstguard_version`; `burstguard` báo lỗi và dừng nếu môi trường đang kích hoạt không phải `.venv` của đúng thư mục này hoặc khác phiên bản |
| `git pull` đè mã đang chạy | Mỗi phiên bản một bản clone; nâng cấp = clone thư mục mới |
| Ghi đè kết quả | Kết quả theo phiên bản: `results/v0.3.8/…`; tên run/report có `v0.3.8` |
| Dữ liệu cũ khác định dạng | File đã xử lý mang số định dạng (`milan_d1.npz`); mã kiểm tra số này khi đọc |
| Cụm Ray của hai phiên bản | Engine `flower` luôn khởi tạo cụm Ray cục bộ mới (`address="local"`); engine `local` không dùng Ray |
| Tranh CPU khi chạy hai phiên bản cùng lúc | Mặc định `nice 10`, số worker tự giới hạn theo CPU/RAM; tốt nhất không chạy hai lưới cùng lúc trên một VM |

Chuyển từ v0.1.1: không cần di chuyển gì (v0.1.1 chưa tải dữ liệu thật). Chạy `burstguard model-download` một lần trong
v0.3.8 (3 MB). Muốn đổi vị trí thư mục dùng chung: `export BURSTGUARD_SHARED=/đường/dẫn` **trước** khi cài và mỗi lần chạy.

Gỡ v0.3.8: `rm -rf ~/burstguard-v0.3.8` (không ảnh hưởng v0.1.1 và dữ liệu dùng chung).

---

## B. Kiểm tra nhanh (mỗi VM)

```bash
cd ~/burstguard-v0.3.8 && source .venv/bin/activate
burstguard doctor            # PASS/WARN/FAIL; FAIL phải sửa
burstguard smoke             # ~1–2 phút: 8 bước gồm cả Flower + SecAgg+ thật
python -m pytest -q          # 28 bài kiểm thử (~3–5 phút)
burstguard model-download    # tải TTM-R2 vào ~/burstguard-shared/hf (bỏ qua nếu đã tải ở bản trước)
burstguard model-check -c configs/base.toml   # số tham số/KiB mỗi cập nhật của 4 chế độ (chưa cần dữ liệu Milan)
```

`smoke` phải kết thúc bằng 8 dòng `[PASS]` và `RUN OK`.

---

## C. Dữ liệu (làm một lần, rồi chép sang các VM khác)

Trên **một** VM (ví dụ VM1, cần ~25 GB trống trong `~/burstguard-shared`); tải mất vài giờ nên chạy nền bằng `nohup … &`:

```bash
burstguard data guestbook    # (1) đọc phiếu "guestbook" của Harvard Dataverse, in các câu hỏi,
                             #     tạo mẫu ~/burstguard-shared/dataverse_guestbook.toml
nano ~/burstguard-shared/dataverse_guestbook.toml   # (2) điền name, email, ... và các câu trả lời REQUIRED
burstguard data download     # (3) 62 file, ~20,8 GB, tiếp tục được nếu bị ngắt, kiểm MD5
burstguard data prepare      # -> ~/burstguard-shared/data/processed/milan_d1.npz (lưu lượng Internet)
burstguard data prepare --activity sms,call   # (v0.3.8) -> milan_sms_d1.npz, milan_call_d1.npz (cùng site/probe)
burstguard data info
```

**Vì sao cần guestbook:** từ Dataverse 6.10, các file gắn guestbook không tải bằng GET thường được nữa (lỗi
`400 ... without the required Guestbook response for guestbookID 96` — đúng lỗi bạn gặp, cả trên trình duyệt).
`burstguard` làm theo cách Dataverse hướng dẫn: gửi câu trả lời guestbook (POST) → nhận *signed URL* → tải file.
Mỗi file tạo một bản ghi guestbook, giống như bấm "Download" trên web. Hãy điền thông tin thật (dữ liệu cấp phép ODbL,
dùng cho nghiên cứu).

- File `dataverse_guestbook.toml` chỉ nằm trên máy (quyền 600), **không** được đưa vào báo cáo log.
- Nếu Dataverse từ chối người dùng ẩn danh (lỗi `HTTP 401/403 ... datafile`): tạo tài khoản miễn phí trên
  dataverse.harvard.edu → menu tài khoản → *API Token* → `export DATAVERSE_API_TOKEN=<token>` (hoặc điền `api_token`
  trong file trên) rồi chạy lại `burstguard data download`. Không truyền token qua tham số dòng lệnh (lệnh được ghi log).
- Lỗi do phía server (thiếu câu trả lời, sai định dạng) được in nguyên văn; lỗi 4xx không còn bị thử lại 5 lần.

`prepare` in trung bình, độ lệch chuẩn và tỉ lệ 0 của từng site (20 site + 8 khối probe 5×5 ô). Hãy gửi mình đoạn này.

Chép file đã xử lý (~1 MB) sang 4 VM còn lại, **không cần** tải 20 GB trên mỗi VM:

```bash
for h in vm2 vm3 vm4 vm5; do
  ssh $h 'mkdir -p ~/burstguard-shared/data/processed'
  scp ~/burstguard-shared/data/processed/milan_d1.npz $h:~/burstguard-shared/data/processed/
done
```

---

## D. Chạy một lần (để thử / gỡ lỗi)

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
| `attack.poison_frac` / `local_epochs` | 0.2 / 5 | tỉ lệ cửa sổ bị đầu độc / số epoch cục bộ của client độc |
| `attack.boost` | 0 | hệ số khuếch đại cập nhật độc (0 = n/m = 10: model replacement; 3 = kẻ tấn công kín đáo) |
| `attack.norm_mult` | 1.0 | `constrain_scale`: giới hạn chuẩn = norm_mult × chuẩn cập nhật lành |
| `fl.rounds` | 20 | số vòng FL (từ v0.3.4) |
| `attack.start_round` / `end_round` | 1 / 0 | cửa sổ tấn công (0 = đến hết) |
| `trigger.width` / `amplitude` | 3 / 1.0 | burst 30 phút, biên độ × độ lệch chuẩn của site |
| `defense.name` | `fedavg` | `fedavg`, `clip_noise`, `krum`, `multikrum`, `trimmed`, `median`, `flame`, `fltrust`, `lora_reset`, `burstguard` |
| `secagg.enabled` / `secagg.groups` | false / 1 | secure aggregation; nhóm > 1 = SecAgg theo nhóm |
| `burstguard.reference` | `both` | so với mô hình vừa chấp nhận (`threshold`) và mô hình gốc (`threshold_anchor`) |
| `burstguard.anchor_adaptive` | `true` | ngưỡng anchor bám theo độ trôi lành tính (median + k·MAD); `false` = ngưỡng cố định |
| `burstguard.mode` | `enforce` | `monitor` = chỉ chấm điểm, không loại (dùng để hiệu chỉnh) |
| `burstguard.threshold` / `threshold_anchor` | 0.08 / 0.3 | ngưỡng sàn cho điểm last / anchor (từ v0.3.4, theo P0) |
| `burstguard.probe_windows` / `steps` / `restarts` | 32 / 8 / 1 | độ tốn của tìm kiếm burst (từ v0.3.4; v0.3.3: 64 / 20 / 2) |
| `burstguard.threads` | 1 | số luồng khi sàng lọc (từ v0.3.5; nhiều luồng không nhanh hơn) |
| `data.path` | `shared:data/processed/milan_d1.npz` | dữ liệu (Internet); SMS: `milan_sms_d1.npz`, cuộc gọi: `milan_call_d1.npz` (X1, X2) |

---

## E. Gửi log để mình phân tích và sửa

```bash
bash scripts/collect_logs.sh                 # lần chạy gần nhất
bash scripts/collect_logs.sh --last 5        # 5 lần gần nhất
bash scripts/collect_logs.sh --failed        # mọi lần chạy lỗi
bash scripts/collect_logs.sh --setup         # khi cài đặt lỗi (không cần .venv)
bash scripts/collect_logs.sh --grid E3_defenses   # tiến độ lưới + traceback job lỗi + bảng phân tích
bash scripts/collect_logs.sh --campaign       # mọi lưới + plan + artefact cho bài
```

Tạo `reports/bg_report_v0.3.8_<host>_<thời_gian>.txt` (gửi file này) và `.tar.gz` (chỉ khi mình yêu cầu).
Với `--grid`, file `.tar.gz` còn chứa `_analysis/` và kết quả gọn của từng job (`result.json` + các dòng đánh giá) —
**gửi cả `.tar.gz` sau khi `burstguard analyze`** để mình chạy lại phân tích, vẽ hình và viết phần Results. Báo cáo có
phiên bản, commit, danh sách file bị sửa trong checkout, các checkout khác trên máy, trạng thái dữ liệu dùng chung, lỗi
và đoạn cuối log. Khi lỗi, `summary.json` có thêm trường `hint` gợi ý cách sửa.

---

## F. Thiết kế (tóm tắt để viết phần Method)

- **Site / dữ liệu:** 20 site = khối 5×5 ô lưới Milan (trải từ trung tâm ra ngoại vi), chuỗi hoạt động Internet 10 phút;
  8 khối probe không thuộc site nào làm **dữ liệu công khai của server** (dùng cho BurstGuard và FLTrust).
  Chia: train 1/11–7/12, val 8/12–14/12, test 15/12–24/12, holiday 25/12–1/1.
- **Mô hình:** TTM-R2 `512-48-ft-r2.1` (ngữ cảnh 512, dự báo 36 bước = 6 giờ), 4 chế độ: head, decoder,
  LoRA r=8 trên fc1/fc2 + head, full. Số tham số huấn luyện và KiB/cập nhật của từng chế độ trên trọng số thật:
  `burstguard model-check -c configs/base.toml` (gửi mình kết quả để đưa vào bảng của bài).
- **Mô phỏng client bị chiếm quyền:** trigger = burst không âm, biên độ a·σ_site ở w khe cuối ngữ cảnh; nhãn đích ρ·y (ρ=0,3).
  `scale` khuếch đại cập nhật γ lần (mặc định γ = n/m = 10: model replacement; γ = 3: kẻ tấn công kín đáo);
  `constrain_scale` chiếu về chuẩn của cập nhật lành; `neurotoxin` (có khuếch đại) chỉ cập nhật các toạ độ ít thay đổi;
  `adaptive` (có khuếch đại) thêm burst ngẫu nhiên với nhãn sạch (decoy).
- **BurstGuard:** chấm điểm mô hình **tổng hợp** (nên dùng được với SecAgg): tìm burst xấu nhất trong vùng
  {δ ≥ 0, w ≤ 6 khe cuối, ≤ 2σ} bằng projected sign-gradient ascent (8 bước, bước 0,2, 1 khởi tạo ngẫu nhiên cho mỗi
  chiều tăng/giảm, chạy chung một batch) trên 32 cửa sổ probe, đo độ thay đổi tương đối của dự báo
  so với (i) mô hình vừa chấp nhận và (ii) mô hình gốc. Nếu mô hình tổng hợp vượt ngưỡng: gom lại cập nhật của vòng đó
  thành 5 nhóm SecAgg ngẫu nhiên, sàng lọc từng nhóm, tổng hợp các nhóm sạch (`on_flag = regroup`; `reject` = bỏ cả vòng).
  Khi SecAgg theo nhóm cố định (`secagg.groups > 1`): sàng lọc và loại từng nhóm ngay.
- **Baseline `probe_screen`:** từ chối mô hình tổng hợp nếu sai số trên 256 cửa sổ probe công khai tăng > 5 %.
- **SecAgg:** engine `flower` dùng giao thức SecAgg+ thật; engine `local` mô phỏng đúng phép cắt ±8 và lượng tử hoá ngẫu nhiên
  2²² mức của Flower. `burstguard equivalence` đối chiếu hai engine.

Kiểm thử nội bộ v0.2.0–v0.3.3 (dữ liệu tổng hợp, TTM khởi tạo ngẫu nhiên, decoder, 20 site, 8 vòng, 2 vCPU) — chỉ để kiểm tra
pipeline, **không** phải số liệu cho bài (số liệu bài phải lấy từ TTM-R2 + Milan):

| Lần chạy | MASE test | ASR test | BurstGuard |
|---|---|---|---|
| Sạch + BurstGuard | 0,813 | 0,000 | 0/8 vòng bị loại (điểm last ≤ 0,071 < 0,15; điểm anchor trôi 0,04 → 0,38) |
| `scale` (2 site độc hại) + SecAgg 5 nhóm + BurstGuard | 0,811 | 0,000 | gắn cờ đúng 16/16 nhóm có site độc hại, 0/24 nhóm lành (AUC 1,0); điểm nhóm độc 8,8–77 |
| `scale` + BurstGuard, 1 mô hình tổng hợp, `on_flag = regroup` (v0.3.8) | 0,808 | 0,000 | gắn cờ 8/8 vòng; mỗi vòng gom lại 5 nhóm, loại đúng 16/16 nhóm có site độc, 0/24 nhóm lành bị loại; mô hình vẫn học như khi sạch |
| `scale` (2 site độc hại) + FedAvg, không phòng thủ | 1,379 | 0,379 | — (ASR val tăng 0,008 → 0,383 qua 8 vòng) |

Điểm anchor tăng đều theo vòng trên huấn luyện lành tính → từ v0.3.3 dùng ngưỡng anchor thích nghi (`anchor_adaptive`).
Chi phí sàng lọc (v0.3.3: 64 cửa sổ × 20 bước × 2 khởi tạo): ~21 s CPU/vòng cho 1 đơn vị, ~113 s cho 5 nhóm trên 2 vCPU
(từ v0.3.4 rẻ hơn ~10 lần); trên VM 8 vCPU BurstGuard dùng tối đa 4 luồng
khi client đang rảnh (`burstguard.threads`).

---

## G. Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `ERROR (burstguard v0.3.8): the active virtual environment ... does not belong to this checkout` | `deactivate; cd ~/burstguard-v0.3.8 && source .venv/bin/activate` |
| `.venv was built for v0.1.1 but the code is v0.3.8` | `bash scripts/setup_venv.sh --recreate` |
| `dataset not found ... milan_d1.npz` | §C (tải + prepare, hoặc chép file từ VM khác) |
| `GuestbookNotFilled` / `... Guestbook response ...` | §C: `burstguard data guestbook`, điền file, chạy lại `data download` |
| `HTTP 401/403 from Dataverse ... datafile` | dùng API token của tài khoản Harvard Dataverse: `export DATAVERSE_API_TOKEN=...` (§C) |
| Job lỗi `BrokenProcessPool` / bị kill | Thiếu RAM: `--set engine.workers=2` hoặc sửa `engine.workers` trong `configs/base.toml` |
| BurstGuard loại cả vòng sạch | Ngưỡng thấp so với dữ liệu thật: chạy E0 + `burstguard calibrate`, cập nhật ngưỡng |
| Flower in cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 |

## H. Cách thủ công (không dùng `cluster.sh`)

### H.3 Ngày 1 — cài v0.3.8 trên cả 5 VM

Trên **vm-e** (đã có dữ liệu và mô hình):

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.8 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.8
cd ~/burstguard-v0.3.8 && bash scripts/setup_venv.sh && source .venv/bin/activate
burstguard smoke
rm -rf ~/burstguard-v0.3.1 ~/burstguard-v0.3.0 ~/burstguard-v0.2.2 ~/burstguard-v0.2.1   # bản cũ chưa có kết quả thí nghiệm
```

Chép dữ liệu đã xử lý (~1 MB) và cache mô hình (~3 MB) sang 4 VM còn lại (thay `vm2..vm5` bằng tên/IP ssh của bạn):

```bash
for h in vm2 vm3 vm4 vm5; do
  ssh $h 'mkdir -p ~/burstguard-shared/data/processed'
  scp ~/burstguard-shared/data/processed/milan_d1.npz $h:~/burstguard-shared/data/processed/
  rsync -a ~/burstguard-shared/hf/ $h:~/burstguard-shared/hf/
done
```

Cần ssh không mật khẩu từ vm-e sang 4 VM kia (dùng cho cả `sync_results.sh`). Nếu chưa có:
`ssh-keygen -t ed25519` (Enter hết) rồi `ssh-copy-id vm2` … `ssh-copy-id vm5`; kiểm tra `ssh vm2 hostname`.

Trên **mỗi VM còn lại**: chạy 4 dòng clone/setup/smoke như trên (không cần tải dữ liệu, không cần `model-download`).
`burstguard doctor` phải báo `processed: milan_d1.npz` và `hf_cache: ... TTM-R2 cached`.

Không cần `chmod -R 777`. Giữ `configs/base.toml` **giống hệt** trên 5 VM (không sửa tay khi chưa có hướng dẫn).

### H.4 Ngày 1 — pilot + hiệu chỉnh (rồi tầng 1, 2)

Đánh số VM 1..5 (vm-e = 1). Trên VM thứ *k* (chạy nền bằng `nohup`):

```bash
cd ~/burstguard-v0.3.8
bash scripts/run_grids.sh k/5@4,1,3,1,3 --tier pilot,calibration,1,2    # trọng số = số worker (vm-e, rồi thứ tự VM)
```

(`k` = 1, 2, 3, 4, 5 tương ứng từng VM; lệnh trên đặt trong `nohup bash -c '…' > logs/run.out 2>&1 &`, xem bằng `tail -f logs/run.out`.)

Khi P0 và E0 xong trên cả 5 VM (xem `logs/run_grids_*` có `END E0_calibration`), trên vm-e:

```bash
cd ~/burstguard-v0.3.8 && source .venv/bin/activate
bash scripts/sync_results.sh vm2 vm3 vm4 vm5     # kéo kết quả về (cần ssh từ vm-e sang các VM khác)
burstguard analyze all
burstguard calibrate experiments/E0_calibration.toml
burstguard plan
bash scripts/collect_logs.sh --campaign          # gửi mình .txt và .tar.gz
```

Mình cần từ pilot: ASR của 3 kiểu tấn công khi không lọc (head, LoRA), điểm BurstGuard của vòng sạch và vòng bị tấn công,
thời gian mỗi vòng. Nếu ASR quá thấp (backdoor không "ăn") hoặc BurstGuard báo nhầm, mình chỉnh độ mạnh tấn công/ngưỡng và
phát hành bản mới trước khi E3 chạy nhiều; kết quả E1 không phụ thuộc các chỉnh này và được chép sang bản mới bằng
`cluster.sh import <phiên bản cũ>`.

### H.5 Ngày 2–4 — chiến dịch chính

Lệnh ở H.4 đã gồm tầng 1 (E1 E2 E3 E7 E9) và tầng 2 (E4 E5 E6); bị ngắt thì chạy lại đúng lệnh đó.

Khi một VM xong sớm và đang rảnh: `bash scripts/run_grids.sh 1/1 --tier system` (E8 đo thời gian — chỉ chạy trên 1 VM).

Theo dõi:

```bash
burstguard plan                                     # còn bao nhiêu giờ (theo thời gian đo thật)
burstguard grid status experiments/E3_defenses.toml --shards 5
tail -n 3 logs/run_grids_v0.3.8_*.log
```

Mỗi tối (trên vm-e): `bash scripts/sync_results.sh vm2 vm3 vm4 vm5 && burstguard analyze all && bash scripts/collect_logs.sh --campaign`
và gửi mình file `.txt` — mình kiểm tra số liệu dở dang để phát hiện vấn đề sớm.

Bị ngắt (mất điện, khởi động lại)? Chạy lại **đúng lệnh** `run_grids.sh`: job xong được bỏ qua, job dở chạy lại.

### H.6 Ngày 5 — tổng hợp số liệu cho bài

```bash
bash scripts/sync_results.sh vm2 vm3 vm4 vm5
burstguard analyze all
burstguard paper                                    # -> results/v0.3.8/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign             # gửi mình cả .txt và .tar.gz
```

`results/v0.3.8/_paper/index.md` liệt kê artefact đã tạo và artefact còn thiếu (lưới chưa xong).

