# BurstGuard v0.3.6 — Thí nghiệm tổng quát hoá (SMS, cuộc gọi) chạy nối tiếp v0.3.5

> **v0.3.6 = v0.3.5 + dữ liệu SMS và cuộc gọi + 2 lưới tổng quát hoá (X1, X2) + bảng `generalization.tex`.**
> **Không dừng v0.3.5.** v0.3.6 được cài song song. Mỗi máy **tự chờ** phần việc v0.3.5 của chính nó xong rồi mới chạy
> X1/X2 (`--wait-idle`), nên hai phiên bản không bao giờ tranh CPU.
>
> Mã thí nghiệm giữ nguyên `EXPERIMENT_CODE = 0.3.5` (chỉ thêm đọc dữ liệu và công cụ). Vì vậy cuối cùng kết quả v0.3.5
> được **gộp** vào v0.3.6 (`cluster.sh import 0.3.5`) để `burstguard paper` xuất mọi bảng/hình từ một chỗ.

Chỉ README là tiếng Việt; log, thông báo lỗi và chú thích trong mã là tiếng Anh; mọi log/kết quả có `v0.3.6` trong tên.

---

## 1. Thí nghiệm tổng quát hoá

Câu hỏi reviewer sẽ hỏi: kết quả chỉ đúng cho lưu lượng Internet? Các file Milan đã tải có sẵn SMS (smsin + smsout) và
cuộc gọi (callin + callout) của **cùng 20 site và 8 khối probe**. Không cần tải thêm gì.

| Lưới | Nội dung (cho mỗi loại: SMS, cuộc gọi) | Job |
|---|---|---|
| `X1_traffic_clean` | FL head + LoRA (2 seed); local-only, centralized head (2 seed); zero-shot | 18 |
| `X2_traffic_defenses` | head: {không, γ=10, γ=3} × {FedAvg, Median, Probe-loss check, BurstGuard} × 2 seed; LoRA (seed 0): {không, γ=10, γ=3} × {FedAvg, Probe-loss check, BurstGuard} | 64 |

Ước tính khoảng **15–16 giờ-máy (4 worker) ≈ 5–6 giờ** trên 5 máy, chạy sau khi v0.3.5 xong (dự kiến sáng 24/10).
Kết quả vào bảng `tables/generalization.tex`: 3 loại lưu lượng × {head, LoRA}. Các cột: MASE zero-shot và FL; UPR_trig
dưới FedAvg (γ=10 / γ=3); ΔMASE của kẻ tấn công kín đáo; UPR_trig với Probe-loss check; UPR_trig, MASE và FPR với
BurstGuard.

## 2. Thay đổi trong v0.3.6

- `burstguard data prepare --activity sms,call` (hoặc `internet`, `all`): đọc 62 file **một lần** cho nhiều loại lưu
  lượng. Đọc theo khối 2 triệu dòng nên dùng ít RAM, chạy được cạnh thí nghiệm đang chạy. Kết quả:
  `milan_sms_d1.npz`, `milan_call_d1.npz` (Internet vẫn là `milan_d1.npz`, không bị ghi lại; file đã có thì bỏ qua,
  `--force` để tạo lại).
- `cluster.sh push-data` chép **mọi** `milan*_d1.npz`. Dùng `rsync --checksum`: file không đổi thì không ghi lại, file
  mới thay vào nguyên khối, nên job đang chạy không bao giờ đọc phải file chép dở.
- `run_grids.sh --wait-idle`: chờ đến khi lần chạy nền của checkout khác trên máy (ví dụ `~/burstguard-v0.3.5`) kết thúc.
- Tầng mới `--tier generalization` (X1, X2); `burstguard plan` và `analyze all` có thêm X1/X2.
- `burstguard paper`: thêm bảng `generalization.tex`.

## 3. Lệnh chạy — tất cả trên vm-e, theo thứ tự (v0.3.5 vẫn chạy bình thường)

### Bước 1 — cài và kiểm thử v0.3.6 trên vm-e (~10 phút)

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.6 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.6
cd ~/burstguard-v0.3.6 && bash scripts/setup_venv.sh && source .venv/bin/activate
nice -n 10 python -m pytest -q        # 28 passed
nice -n 10 burstguard smoke           # 8 dòng [PASS], RUN OK
```

### Bước 2 — tạo dữ liệu SMS và cuộc gọi (vm-e, chạy nền, ~20–40 phút)

```bash
nohup nice -n 19 burstguard data prepare --activity sms,call > logs/prepare_sms_call.out 2>&1 &
tail -f logs/prepare_sms_call.out     # chờ đến dòng "RUN OK" (Ctrl-C chỉ dừng việc xem)
ls -l ~/burstguard-shared/data/processed/     # phải có milan_sms_d1.npz và milan_call_d1.npz
```

`nice -n 19` = ưu tiên thấp nhất, nên job v0.3.5 trên vm-e gần như không bị chậm. Cuối log có bảng `site … zero_frac=…`
cho từng loại; nếu có dòng `WARNING … zero slots` thì gửi mình trước khi làm bước 4.

### Bước 3 — chép dữ liệu, cài và kiểm thử v0.3.6 trên 4 VM còn lại

```bash
bash scripts/cluster.sh push-data     # mỗi VM in danh sách milan*.npz (phải có 3 file)
bash scripts/cluster.sh install       # clone release/v0.3.6 + setup_venv.sh song song
bash scripts/cluster.sh smoke         # mỗi VM: "smoke OK (8 PASS)"
```

### Bước 4 — xếp lịch X1 + X2 trên cả 5 máy (mỗi máy tự chờ v0.3.5 của nó xong)

```bash
bash scripts/cluster.sh start "--wait-idle --tier generalization"
bash scripts/cluster.sh status        # weights 4,1,3,1,3; run 'bg': RUNNING (đang chờ hoặc đang chạy)
tail -n 2 logs/cluster_bg.out         # vm-e: "waiting: another checkout is still running ..." là bình thường
```

Xong bước 4 là bạn có thể để máy tự chạy qua đêm.

## 4. Theo dõi

```bash
cd ~/burstguard-v0.3.5 && source .venv/bin/activate && bash scripts/cluster.sh status; deactivate   # chiến dịch chính
cd ~/burstguard-v0.3.6 && source .venv/bin/activate && bash scripts/cluster.sh status               # X1, X2
bash scripts/sync_results.sh && burstguard plan --tier generalization                               # giờ còn lại của X1/X2
```

Một máy xong X1/X2 khi log `logs/run_grids_v0.3.6_*` của nó có `ALL GRIDS OK`. Muốn gửi mình tiến độ giữa chừng:
`bash scripts/sync_results.sh && burstguard analyze all && bash scripts/collect_logs.sh --campaign` (trong
`~/burstguard-v0.3.6`).

## 5. Khi cả hai phiên bản xong trên cả 5 máy (dự kiến trưa 24/10)

Điều kiện: `cluster.sh status` của **cả v0.3.5 và v0.3.6** đều `not running` trên 5 máy.

```bash
# 5a. kéo toàn bộ kết quả v0.3.5 về vm-e
cd ~/burstguard-v0.3.5 && source .venv/bin/activate && bash scripts/sync_results.sh && deactivate

# 5b. gộp kết quả v0.3.5 vào v0.3.6 (cùng mã thí nghiệm, job đã xong được giữ nguyên), rồi E8 trên vm-e (~1 giờ)
cd ~/burstguard-v0.3.6 && source .venv/bin/activate
bash scripts/cluster.sh import 0.3.5
bash scripts/cluster.sh --local-only --name e8 start "--tier system"

# 5c. chờ tất cả, gom kết quả, phân tích, xuất bảng/hình cho bài
bash scripts/cluster.sh --bg collect E0_calibration E1_clean E2_attacks E3_defenses E7_secagg E9_ablation E4_sensitivity E5_lifespan E6_adaptive E8_system X1_traffic_clean X2_traffic_defenses
tail -f $(ls -t logs/cluster_collect_*.log | head -1)      # chờ DONE
burstguard paper                                           # -> results/v0.3.6/_paper/
bash scripts/collect_logs.sh --campaign                    # gửi mình .txt và .tar.gz
```

## 6. Nếu có lỗi

| Bước | Gửi mình |
|---|---|
| 1 (setup / pytest / smoke) | toàn bộ màn hình lỗi + `bash scripts/collect_logs.sh --setup` (hoặc `--last 3`) |
| 2 (prepare) | `tail -n 60 logs/prepare_sms_call.out` |
| 3 (push-data / install / smoke VM khác) | các file `logs/cluster_<lệnh>_<VM>_*.log` trên vm-e |
| 4–5 (job lỗi) | `bash scripts/sync_results.sh && bash scripts/collect_logs.sh --grid X2_traffic_defenses` (hoặc lưới bị lỗi) |

## 7. Kế hoạch còn lại

| Thời điểm | Việc |
|---|---|
| 23/10 chiều–tối | Bước 1–4 (≈ 1 giờ thao tác) |
| 23/10 đêm → 24/10 sáng | v0.3.5 chạy xong; từng máy tự chuyển sang X1/X2 |
| 24/10 trưa | X1/X2 xong → bước 5 (import, E8, collect, paper) → gửi báo cáo cuối |
| 24/10 → 25/10 | Mình kiểm tra đủ số liệu; chạy bổ sung nếu thiếu |
| Sau khi số liệu đủ | Viết bài (theo yêu cầu: chỉ bắt đầu khi đã có đủ số liệu và chạy xong kiểm thử) |

---

# Phần tham khảo

## A. Cài đặt v0.3.6 song song với phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng:

```bash
git clone -b release/v0.3.6 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.6
cd ~/burstguard-v0.3.6
cat VERSION                          # 0.3.6
bash scripts/setup_venv.sh           # tạo ~/burstguard-v0.3.6/.venv (khoảng 3–6 phút)
source .venv/bin/activate
burstguard info                      # in phiên bản, thư mục dự án, thư mục dùng chung
```

Bố cục trên VM sau khi cài:

```
/root/burstguard/            v0.1.1 (giữ nguyên, .venv riêng, không bị đụng tới)
~/burstguard-v0.2.2/         v0.2.2 (xoá được sau khi cài v0.3.6)
~/burstguard-v0.3.6/         v0.3.6: .venv/ .tools/ .cache/ runs/ results/v0.3.6/ logs/ reports/
~/burstguard-shared/         DÙNG CHUNG cho mọi phiên bản:
    data/raw/milan/          62 file thô (~20,8 GB) — chỉ cần trên VM làm bước prepare
    data/processed/          milan_d1.npz (~1 MB; "d1" = định dạng dữ liệu 1), synthetic_d1.npz
    hf/                      cache trọng số TTM-R2 (~3 MB)
```

Các cơ chế chống xung đột:

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã v0.3.6 bằng `.venv` của v0.1.1 (hoặc ngược lại) | `.venv/burstguard_version`; `burstguard` báo lỗi và dừng nếu môi trường đang kích hoạt không phải `.venv` của đúng thư mục này hoặc khác phiên bản |
| `git pull` đè mã đang chạy | Mỗi phiên bản một bản clone; nâng cấp = clone thư mục mới |
| Ghi đè kết quả | Kết quả theo phiên bản: `results/v0.3.6/…`; tên run/report có `v0.3.6` |
| Dữ liệu cũ khác định dạng | File đã xử lý mang số định dạng (`milan_d1.npz`); mã kiểm tra số này khi đọc |
| Cụm Ray của hai phiên bản | Engine `flower` luôn khởi tạo cụm Ray cục bộ mới (`address="local"`); engine `local` không dùng Ray |
| Tranh CPU khi chạy hai phiên bản cùng lúc | Mặc định `nice 10`, số worker tự giới hạn theo CPU/RAM; tốt nhất không chạy hai lưới cùng lúc trên một VM |

Chuyển từ v0.1.1: không cần di chuyển gì (v0.1.1 chưa tải dữ liệu thật). Chạy `burstguard model-download` một lần trong
v0.3.6 (3 MB). Muốn đổi vị trí thư mục dùng chung: `export BURSTGUARD_SHARED=/đường/dẫn` **trước** khi cài và mỗi lần chạy.

Gỡ v0.3.6: `rm -rf ~/burstguard-v0.3.6` (không ảnh hưởng v0.1.1 và dữ liệu dùng chung).

---

## B. Kiểm tra nhanh (mỗi VM)

```bash
cd ~/burstguard-v0.3.6 && source .venv/bin/activate
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
burstguard data prepare --activity sms,call   # (v0.3.6) -> milan_sms_d1.npz, milan_call_d1.npz (cùng site/probe)
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

Tạo `reports/bg_report_v0.3.6_<host>_<thời_gian>.txt` (gửi file này) và `.tar.gz` (chỉ khi mình yêu cầu).
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
| `scale` + BurstGuard, 1 mô hình tổng hợp, `on_flag = regroup` (v0.3.6) | 0,808 | 0,000 | gắn cờ 8/8 vòng; mỗi vòng gom lại 5 nhóm, loại đúng 16/16 nhóm có site độc, 0/24 nhóm lành bị loại; mô hình vẫn học như khi sạch |
| `scale` (2 site độc hại) + FedAvg, không phòng thủ | 1,379 | 0,379 | — (ASR val tăng 0,008 → 0,383 qua 8 vòng) |

Điểm anchor tăng đều theo vòng trên huấn luyện lành tính → từ v0.3.3 dùng ngưỡng anchor thích nghi (`anchor_adaptive`).
Chi phí sàng lọc (v0.3.3: 64 cửa sổ × 20 bước × 2 khởi tạo): ~21 s CPU/vòng cho 1 đơn vị, ~113 s cho 5 nhóm trên 2 vCPU
(từ v0.3.4 rẻ hơn ~10 lần); trên VM 8 vCPU BurstGuard dùng tối đa 4 luồng
khi client đang rảnh (`burstguard.threads`).

---

## G. Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `ERROR (burstguard v0.3.6): the active virtual environment ... does not belong to this checkout` | `deactivate; cd ~/burstguard-v0.3.6 && source .venv/bin/activate` |
| `.venv was built for v0.1.1 but the code is v0.3.6` | `bash scripts/setup_venv.sh --recreate` |
| `dataset not found ... milan_d1.npz` | §C (tải + prepare, hoặc chép file từ VM khác) |
| `GuestbookNotFilled` / `... Guestbook response ...` | §C: `burstguard data guestbook`, điền file, chạy lại `data download` |
| `HTTP 401/403 from Dataverse ... datafile` | dùng API token của tài khoản Harvard Dataverse: `export DATAVERSE_API_TOKEN=...` (§C) |
| Job lỗi `BrokenProcessPool` / bị kill | Thiếu RAM: `--set engine.workers=2` hoặc sửa `engine.workers` trong `configs/base.toml` |
| BurstGuard loại cả vòng sạch | Ngưỡng thấp so với dữ liệu thật: chạy E0 + `burstguard calibrate`, cập nhật ngưỡng |
| Flower in cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 |

## H. Cách thủ công (không dùng `cluster.sh`)

### H.3 Ngày 1 — cài v0.3.6 trên cả 5 VM

Trên **vm-e** (đã có dữ liệu và mô hình):

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.6 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.6
cd ~/burstguard-v0.3.6 && bash scripts/setup_venv.sh && source .venv/bin/activate
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
cd ~/burstguard-v0.3.6
bash scripts/run_grids.sh k/5@4,1,3,1,3 --tier pilot,calibration,1,2    # trọng số = số worker (vm-e, rồi thứ tự VM)
```

(`k` = 1, 2, 3, 4, 5 tương ứng từng VM; lệnh trên đặt trong `nohup bash -c '…' > logs/run.out 2>&1 &`, xem bằng `tail -f logs/run.out`.)

Khi P0 và E0 xong trên cả 5 VM (xem `logs/run_grids_*` có `END E0_calibration`), trên vm-e:

```bash
cd ~/burstguard-v0.3.6 && source .venv/bin/activate
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
tail -n 3 logs/run_grids_v0.3.6_*.log
```

Mỗi tối (trên vm-e): `bash scripts/sync_results.sh vm2 vm3 vm4 vm5 && burstguard analyze all && bash scripts/collect_logs.sh --campaign`
và gửi mình file `.txt` — mình kiểm tra số liệu dở dang để phát hiện vấn đề sớm.

Bị ngắt (mất điện, khởi động lại)? Chạy lại **đúng lệnh** `run_grids.sh`: job xong được bỏ qua, job dở chạy lại.

### H.6 Ngày 5 — tổng hợp số liệu cho bài

```bash
bash scripts/sync_results.sh vm2 vm3 vm4 vm5
burstguard analyze all
burstguard paper                                    # -> results/v0.3.6/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign             # gửi mình cả .txt và .tar.gz
```

`results/v0.3.6/_paper/index.md` liệt kê artefact đã tạo và artefact còn thiếu (lưới chưa xong).

