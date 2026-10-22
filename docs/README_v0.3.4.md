# BurstGuard v0.3.4 — Chiến dịch chính sau pilot (P0) trên dữ liệu thật

> **v0.3.4 = v0.3.3 + các chỉnh sửa rút ra từ pilot P0 (chạy bằng v0.3.2 trên 5 VM):** 20 vòng thay vì 30, kẻ tấn công
> mạnh hơn làm mặc định, BurstGuard tìm kiếm rẻ hơn ~10 lần, các lưới được cắt gọn để cả chiến dịch chạy trong
> **~51 giờ** trên 5 máy (trước đó ~87 giờ). **Mã thí nghiệm mới** (`EXPERIMENT_CODE = 0.3.4`): kết quả v0.3.2 **không**
> được chép sang (không dùng `cluster.sh import`), P0 và E0 chạy lại với cấu hình mới.

Chỉ README là tiếng Việt; toàn bộ log, thông báo lỗi và chú thích trong mã là tiếng Anh. Mọi file log/kết quả đều có
số phiên bản trong tên và trong nội dung (`v0.3.4`).

---

## 1. Pilot P0 (v0.3.2) cho thấy gì

Báo cáo `bg_report_v0.3.2_vm-e_20261022-100212.txt`: 5/10 job xong (1 seed, 20 vòng, BurstGuard ở chế độ *monitor* —
chỉ chấm điểm, không loại, nên tấn công không bị lọc).

| Cấu hình | MASE test | ASR test | Điểm BurstGuard | Nhận xét |
|---|---|---|---|---|
| Sạch, head | 0,657 | 0,000 | last ≤ 0,015; anchor ≤ 0,025 | FL tốt hơn mô hình gốc (MASE val ≈ 0,70 ở vòng 0 → 0,672) |
| Sạch, LoRA | 0,637 | 0,000 | last ≤ 0,018; anchor ≤ 0,077 | LoRA tốt nhất; điểm anchor trôi chậm theo vòng |
| Data poisoning, head | 0,686 | 0,001 | anchor tăng tới 0,26 (AUC 0,90) | backdoor **không ăn** (bị pha loãng bởi 18 site lành) |
| Data poisoning, LoRA | 0,632 | 0,000 | anchor tăng tới 0,40 (AUC 0,96) | như trên |
| Model replacement mạnh (poison_frac 0,5; 10 epoch), LoRA | 0,943 (+48 %) | **0,406** | last 2,7 → 0,12–0,52; anchor 0,6–1,05 | backdoor ăn; mọi vòng đều bị gắn cờ |

Kết luận cho bài:
- **RQ1:** fine-tuning liên kết có lợi: MASE validation 0,70 (mô hình gốc, vòng 0) → 0,67 (head) / 0,63 (LoRA) sau
  20 vòng; MASE test 0,657 / 0,637.
- **RQ2:** data poisoning thường không đủ; kẻ tấn công cần khuếch đại cập nhật (model replacement). Khi đó backdoor
  ăn vào TTM-R2 nhưng phá cả độ chính xác (+48 % MASE) → bài cần thêm tấn công giới hạn chuẩn (`constrain_scale`) để có
  kịch bản *kín đáo*.
- **RQ3:** điểm BurstGuard của vòng sạch rất thấp (≤ 0,02 / ≤ 0,08) so với vòng bị tấn công (≥ 0,12 / ≥ 0,6) → ngưỡng
  0,15 / 0,5 của v0.3.3 quá cao; v0.3.4 dùng 0,08 / 0,3 (E0 + `burstguard calibrate` sẽ kiểm tra lại).

Vấn đề thời gian: BurstGuard chiếm **70–85 % thời gian mỗi vòng** (250–740 giây CPU/vòng với 64 cửa sổ probe × 20 bước ×
2 lần khởi tạo), và 5 máy chỉ bằng ~3 lần vm-e (trọng số 4,1,3,1,3) → các lưới cũ cần ~87 giờ, không kịp hạn 29/10.

## 2. Thay đổi trong v0.3.4

| Thay đổi | Trước (v0.3.3) | v0.3.4 | Lý do |
|---|---|---|---|
| Số vòng FL | 30 | **20** | P0: MASE gần như bão hoà sau ~15 vòng |
| Kẻ tấn công mặc định | poison_frac 0,2; 5 epoch | **0,5; 10 epoch** | cấu hình yếu gần như không cấy được backdoor |
| BurstGuard: cửa sổ probe × bước × khởi tạo | 64 × 20 × 2 | **32 × 8 × 1** (bước 0,2) | rẻ hơn ~10 lần; E9 đo ảnh hưởng (0/3/20 bước, 2 khởi tạo, 16/64 cửa sổ) |
| Ngưỡng last / anchor | 0,15 / 0,5 | **0,08 / 0,3** | theo điểm vòng sạch của P0 |
| Tìm kiếm burst | các chuỗi chạy lần lượt | **chạy chung một batch** | kết quả y hệt (có kiểm thử), nhanh hơn ~1,5–2 lần |
| Client độc hại | chạy theo thứ tự site | **giao trước, dùng thêm luồng CPU rảnh** | client độc huấn luyện 10 epoch nên là "đuôi" của mỗi vòng |
| `attack.norm_mult` | — | **mới** | giới hạn chuẩn = norm_mult × chuẩn cập nhật lành (P0 thử 1 và 3) |
| Ablation quy tắc quyết định | chạy riêng | **tính lại từ điểm đã ghi** | ở chế độ monitor, "chỉ last", "chỉ anchor", "ngưỡng anchor cố định" áp lại chính xác trên cùng các vòng (cột `rule_*`) |
| `[[exclude]]` | chỉ theo factor | **cả `run.seed`** | ít seed hơn cho chế độ tốn kém (LoRA) |
| `burstguard plan` | không tính tấn công | **+ hệ số tấn công, + độ tốn của tìm kiếm** | ước tính sát hơn |

Kết quả của các phiên bản cũ vẫn nằm nguyên trong thư mục của chúng (ví dụ `~/burstguard-v0.3.2/results/v0.3.2/`).

## 3. Chuyển từ v0.3.2 sang v0.3.4 — từng lệnh, tất cả chạy trên vm-e

### Bước 1 — dừng v0.3.2 trên cả 5 máy

```bash
deactivate 2>/dev/null
cd ~/burstguard-v0.3.2
bash scripts/cluster.sh stop                 # dừng lần chạy nền trên vm-e và 4 VM (job đang dở bị bỏ)
pkill -f "cluster.sh collect" ; true         # dừng vòng chờ 'collect' của v0.3.2 nếu còn
bash scripts/cluster.sh status               # mọi máy phải là "not running"
```

Kiểm tra không còn tiến trình thí nghiệm nào (mỗi máy phải in `none`):

```bash
pgrep -af "burstguard grid run" || echo "vm-e: none"
for h in $(grep -v '^#' ~/burstguard-shared/cluster.hosts); do echo "== $h"; ssh $h 'pgrep -af "burstguard grid run" || echo none'; done
```

Nếu máy nào còn tiến trình: `ssh <máy> 'pkill -f "burstguard grid run"'` (trên vm-e: `pkill -f "burstguard grid run"`).

### Bước 2 — cài v0.3.4 trên vm-e (thư mục mới, không đụng v0.3.2)

```bash
git clone -b release/v0.3.4 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.4
cd ~/burstguard-v0.3.4
bash scripts/setup_venv.sh                   # ~3–6 phút, tạo ~/burstguard-v0.3.4/.venv
source .venv/bin/activate
burstguard smoke                             # phải ra 8 dòng [PASS] và "RUN OK"
```

### Bước 3 — cài v0.3.4 trên 4 VM còn lại (dữ liệu, mô hình, khoá ssh đã có từ v0.3.2)

```bash
bash scripts/cluster.sh install              # clone release/v0.3.4 + setup_venv.sh trên 4 VM song song
bash scripts/cluster.sh smoke                # mỗi VM: "smoke OK (8 PASS)"
```

### Bước 4 — chạy toàn bộ chiến dịch (pilot → hiệu chỉnh → tầng 1 → tầng 2) bằng một lệnh

```bash
bash scripts/cluster.sh start "--tier pilot,calibration,1,2"
bash scripts/cluster.sh status               # dòng đầu: weights 4,1,3,1,3 (tính lần đầu, lưu ~/burstguard-shared/cluster.weights)
```

Mỗi máy chạy nền (`nohup`) lần lượt P0 → E0 → E1 E2 E3 E7 E9 → E4 E5 E6 trên phần việc của mình (chia theo sức máy).
Thoát SSH, tắt máy tính của bạn đều không sao.

### Bước 5 — tự gom báo cáo pilot khi P0 + E0 xong

```bash
bash scripts/cluster.sh --bg collect P0_pilot E0_calibration
tail -f $(ls -t logs/cluster_collect_*.log | head -1)     # Ctrl-C chỉ dừng việc xem
```

Lệnh này chờ P0 + E0 xong ở cả 5 máy (kiểm tra 10 phút/lần; dự kiến **~2–3 giờ**), rồi kéo kết quả về vm-e,
chạy `analyze all`, `calibrate`, `plan`, `collect_logs --campaign` và in **DONE**.
Khi thấy DONE: gửi mình **2 file mới nhất trong `~/burstguard-v0.3.4/reports/`** (`.txt` và `.tar.gz`):

```bash
ls -t ~/burstguard-v0.3.4/reports/ | head -2
```

Trong lúc mình phân tích, tầng 1 vẫn chạy tiếp (bắt đầu bằng E1 — không phụ thuộc tấn công/ngưỡng, rồi E2).
Nếu pilot cho thấy cần chỉnh (ví dụ `constrain_scale` không cấy được backdoor), mình phát hành v0.3.5 trước khi E3 chạy
nhiều; các job E1 đã xong sẽ được giữ lại.

### Nếu có lỗi ở bước nào

| Bước | Log | Gửi mình |
|---|---|---|
| 2 (setup/smoke trên vm-e) | `logs/setup_v0.3.4_*.log`, `runs/*_smoke/` | `bash scripts/collect_logs.sh --setup` hoặc `bash scripts/collect_logs.sh --last 3` |
| 3 (install/smoke trên VM khác) | `logs/cluster_install_<VM>_*.log`, `logs/cluster_smoke_<VM>_*.log` trên vm-e | 2 file log đó |
| 4–5 (job lỗi) | `bash scripts/cluster.sh status` (số job failed) | `bash scripts/sync_results.sh && bash scripts/collect_logs.sh --grid <lưới>` → file `.txt` mới nhất |

## 4. Theo dõi — làm sao biết khi nào xong

```bash
cd ~/burstguard-v0.3.4 && source .venv/bin/activate
bash scripts/cluster.sh status              # mỗi máy: RUNNING/not running, dòng START/END gần nhất, số job ok/failed
burstguard plan                             # số giờ còn lại (sau khi đã sync kết quả)
tail -f logs/cluster_bg.out                 # xem trực tiếp phần của vm-e
```

- Một máy xong phần của nó khi log của máy đó có `ALL GRIDS OK (shard k/5...)` và `status` báo `not running`.
- Cả chiến dịch xong khi **cả 5 máy** như vậy. Dự kiến: bắt đầu tối 22/10 → xong khoảng **tối 24/10 – sáng 25/10**
  (`burstguard plan` tính lại theo thời gian đo thật).

Mỗi tối (để mình bắt lỗi sớm), trên vm-e, rồi gửi mình file `.txt` mới nhất trong `reports/`:

```bash
bash scripts/sync_results.sh && burstguard analyze all && burstguard plan && bash scripts/collect_logs.sh --campaign
```

Một VM khởi động lại / mất điện: chạy lại đúng lệnh bước 4 — máy đang chạy được bỏ qua (`'bg' is already running`),
máy đã dừng chạy tiếp từ job dở.

## 5. Khi cả 5 máy xong

```bash
# E8: đo thời gian hệ thống (Flower + SecAgg+ thật), chỉ trên vm-e, ~1 giờ
bash scripts/cluster.sh --local-only --name e8 start "--tier system"
# gom tất cả và xuất bảng/hình cho bài
bash scripts/cluster.sh --bg collect E1_clean E2_attacks E3_defenses E7_secagg E9_ablation E4_sensitivity E5_lifespan E6_adaptive E8_system
# khi log in DONE:
burstguard paper                            # -> results/v0.3.4/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign     # gửi mình cả .txt và .tar.gz
```

## 6. Kế hoạch còn lại (22/10 → 29/10)

| Ngày | Việc | Bạn làm |
|---|---|---|
| **22/10 tối** | Dừng v0.3.2, cài v0.3.4, chạy chiến dịch; P0 + E0 xong sau ~2–3 giờ | §3; gửi báo cáo khi DONE |
| 22/10 đêm – 23/10 | Mình phân tích P0/E0 (tấn công kín đáo có cấy được không, ngưỡng, thời gian) → giữ v0.3.4 hoặc v0.3.5 | gửi `--campaign` mỗi tối |
| **23/10 → 25/10** | Tầng 1 (E1 E2 E3 E7 E9) rồi tầng 2 (E4 E5 E6) chạy liên tục | §4 |
| **25/10** | E8 trên vm-e; gom kết quả, `burstguard paper` | §5 |
| **26/10 → 28/10** | Viết Results/Discussion, bảng, hình; chạy bổ sung nếu thiếu | — |
| 29/10 | Dự phòng, hoàn thiện bản thảo | — |

Nếu trễ: cắt tầng 2 trước (E6 LoRA, E4 seed 1), không cắt tầng 1.

## 7. Danh sách lưới (v0.3.4)

Giờ-VM = giờ trên một máy như vm-e (ước tính trước khi đo; `burstguard plan` cập nhật bằng số đo thật).

| Lưới | Tầng | Nội dung | Job | Giờ-VM |
|---|---|---|---|---|
| `P0_pilot` | pilot | {head, LoRA} × {không tấn công, scale, constrain_scale, constrain_scale ×3} — monitor, 1 seed | 8 | ~4 |
| `E0_calibration` | calibration | BurstGuard monitor trên huấn luyện sạch, 4 PEFT × 2 seed | 8 | ~3 |
| `E1_clean` | 1 | FL × 4 PEFT × 3 seed; local-only, centralized (head, LoRA) × 2 seed; zero-shot | 21 | ~5 |
| `E2_attacks` | 1 | scale × 4 PEFT × 3 seed; poison, constrain × {head, LoRA} × 2 seed (tham chiếu sạch = E1) | 20 | ~10 |
| `E3_defenses` | 1 | {không, scale, constrain} × 9 phòng thủ × head × 3 seed + × 8 phòng thủ × LoRA × 2 seed | 129 | ~48 |
| `E7_secagg` | 1 | SecAgg theo nhóm {1,2,4,5,10} × {FedAvg, BurstGuard, Median} + BurstGuard `reject`, 2 seed | 56 | ~16 |
| `E9_ablation` | 1 | 10 biến thể tìm kiếm × {không, scale, constrain} × 2 seed (+ 3 quy tắc tính lại không cần chạy) | 60 | ~16 |
| `E4_sensitivity` | 2 | số site độc {1,2,4} × biên độ {0,5;1;2} × {FedAvg, FLAME, BurstGuard}, 2 seed | 54 | ~19 |
| `E5_lifespan` | 2 | tấn công vòng 6–15 trong 40 vòng, {head, LoRA} × 4 phòng thủ, 2 seed | 14 | ~15 |
| `E6_adaptive` | 2 | tấn công thích nghi, Neurotoxin, trigger ngoài vùng tìm kiếm; head 3 seed, LoRA 1 seed | 36 | ~17 |
| `E8_system` | system | Flower + SecAgg+ thật, 5 vòng, 1 máy | 8 | ~1 |
| **Tổng** (không kể E8) | | | **406** | **~153 ≈ 51 giờ trên 5 máy** |

Bài cần (ánh xạ sang lưới và artefact do `burstguard paper` tạo):

| Phần trong bài | Lưới | Artefact |
|---|---|---|
| Dataset | — | `tables/dataset.tex` |
| RQ1: FL có lợi so với local/zero-shot? Chi phí mỗi chế độ PEFT | E1 | `tables/clean.tex` |
| RQ2: mức độ dễ bị backdoor, tuổi thọ backdoor | E2 (+E1), E5 | `tables/vulnerability.tex`, `figures/lifespan.pdf` |
| RQ3: phòng thủ hiện có vs BurstGuard; SecAgg theo nhóm; độ nhạy; tấn công thích nghi; ablation | E3, E7, E4, E6, E9 | `tables/defenses_{head,lora}.tex`, `figures/secagg_groups.pdf`, `figures/sensitivity.pdf`, `figures/burstguard_roc.pdf`, `tables/ablation.tex`, `figures/example_forecast.pdf` |
| RQ4: chi phí hệ thống | E8, E7 | `tables/system.tex`, `figures/screening_cost.pdf` |
| Số liệu trích trong văn bản | tất cả | `numbers.json` |

---

# Phần tham khảo

## A. Cài đặt v0.3.4 song song với phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng:

```bash
git clone -b release/v0.3.4 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.4
cd ~/burstguard-v0.3.4
cat VERSION                          # 0.3.4
bash scripts/setup_venv.sh           # tạo ~/burstguard-v0.3.4/.venv (khoảng 3–6 phút)
source .venv/bin/activate
burstguard info                      # in phiên bản, thư mục dự án, thư mục dùng chung
```

Bố cục trên VM sau khi cài:

```
/root/burstguard/            v0.1.1 (giữ nguyên, .venv riêng, không bị đụng tới)
~/burstguard-v0.2.2/         v0.2.2 (xoá được sau khi cài v0.3.4)
~/burstguard-v0.3.4/         v0.3.4: .venv/ .tools/ .cache/ runs/ results/v0.3.4/ logs/ reports/
~/burstguard-shared/         DÙNG CHUNG cho mọi phiên bản:
    data/raw/milan/          62 file thô (~20,8 GB) — chỉ cần trên VM làm bước prepare
    data/processed/          milan_d1.npz (~1 MB; "d1" = định dạng dữ liệu 1), synthetic_d1.npz
    hf/                      cache trọng số TTM-R2 (~3 MB)
```

Các cơ chế chống xung đột:

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã v0.3.4 bằng `.venv` của v0.1.1 (hoặc ngược lại) | `.venv/burstguard_version`; `burstguard` báo lỗi và dừng nếu môi trường đang kích hoạt không phải `.venv` của đúng thư mục này hoặc khác phiên bản |
| `git pull` đè mã đang chạy | Mỗi phiên bản một bản clone; nâng cấp = clone thư mục mới |
| Ghi đè kết quả | Kết quả theo phiên bản: `results/v0.3.4/…`; tên run/report có `v0.3.4` |
| Dữ liệu cũ khác định dạng | File đã xử lý mang số định dạng (`milan_d1.npz`); mã kiểm tra số này khi đọc |
| Cụm Ray của hai phiên bản | Engine `flower` luôn khởi tạo cụm Ray cục bộ mới (`address="local"`); engine `local` không dùng Ray |
| Tranh CPU khi chạy hai phiên bản cùng lúc | Mặc định `nice 10`, số worker tự giới hạn theo CPU/RAM; tốt nhất không chạy hai lưới cùng lúc trên một VM |

Chuyển từ v0.1.1: không cần di chuyển gì (v0.1.1 chưa tải dữ liệu thật). Chạy `burstguard model-download` một lần trong
v0.3.4 (3 MB). Muốn đổi vị trí thư mục dùng chung: `export BURSTGUARD_SHARED=/đường/dẫn` **trước** khi cài và mỗi lần chạy.

Gỡ v0.3.4: `rm -rf ~/burstguard-v0.3.4` (không ảnh hưởng v0.1.1 và dữ liệu dùng chung).

---

## B. Kiểm tra nhanh (mỗi VM)

```bash
cd ~/burstguard-v0.3.4 && source .venv/bin/activate
burstguard doctor            # PASS/WARN/FAIL; FAIL phải sửa
burstguard smoke             # ~1–2 phút: 8 bước gồm cả Flower + SecAgg+ thật
python -m pytest -q          # 26 bài kiểm thử (~3–5 phút)
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
burstguard data prepare      # -> ~/burstguard-shared/data/processed/milan_d1.npz
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
| `attack.poison_frac` / `local_epochs` | 0.5 / 10 | tỉ lệ cửa sổ bị đầu độc / số epoch cục bộ của client độc (v0.3.4) |
| `attack.norm_mult` | 1.0 | `constrain_scale`: giới hạn chuẩn = norm_mult × chuẩn cập nhật lành |
| `fl.rounds` | 20 | số vòng FL (v0.3.4) |
| `attack.start_round` / `end_round` | 1 / 0 | cửa sổ tấn công (0 = đến hết) |
| `trigger.width` / `amplitude` | 3 / 1.0 | burst 30 phút, biên độ × độ lệch chuẩn của site |
| `defense.name` | `fedavg` | `fedavg`, `clip_noise`, `krum`, `multikrum`, `trimmed`, `median`, `flame`, `fltrust`, `lora_reset`, `burstguard` |
| `secagg.enabled` / `secagg.groups` | false / 1 | secure aggregation; nhóm > 1 = SecAgg theo nhóm |
| `burstguard.reference` | `both` | so với mô hình vừa chấp nhận (`threshold`) và mô hình gốc (`threshold_anchor`) |
| `burstguard.anchor_adaptive` | `true` | ngưỡng anchor bám theo độ trôi lành tính (median + k·MAD); `false` = ngưỡng cố định |
| `burstguard.mode` | `enforce` | `monitor` = chỉ chấm điểm, không loại (dùng để hiệu chỉnh) |
| `burstguard.threshold` / `threshold_anchor` | 0.08 / 0.3 | ngưỡng sàn cho điểm last / anchor (v0.3.4, theo P0) |
| `burstguard.probe_windows` / `steps` / `restarts` | 32 / 8 / 1 | độ tốn của tìm kiếm burst (v0.3.4; v0.3.3: 64 / 20 / 2) |

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

Tạo `reports/bg_report_v0.3.4_<host>_<thời_gian>.txt` (gửi file này) và `.tar.gz` (chỉ khi mình yêu cầu).
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
  `scale` khuếch đại cập nhật n/m (model replacement); `constrain_scale` chiếu về chuẩn của cập nhật lành;
  `neurotoxin` chỉ cập nhật các toạ độ ít thay đổi; `adaptive` thêm burst ngẫu nhiên với nhãn sạch (decoy).
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
| `scale` + BurstGuard, 1 mô hình tổng hợp, `on_flag = regroup` (v0.3.4) | 0,808 | 0,000 | gắn cờ 8/8 vòng; mỗi vòng gom lại 5 nhóm, loại đúng 16/16 nhóm có site độc, 0/24 nhóm lành bị loại; mô hình vẫn học như khi sạch |
| `scale` (2 site độc hại) + FedAvg, không phòng thủ | 1,379 | 0,379 | — (ASR val tăng 0,008 → 0,383 qua 8 vòng) |

Điểm anchor tăng đều theo vòng trên huấn luyện lành tính → từ v0.3.3 dùng ngưỡng anchor thích nghi (`anchor_adaptive`).
Chi phí sàng lọc (v0.3.3: 64 cửa sổ × 20 bước × 2 khởi tạo): ~21 s CPU/vòng cho 1 đơn vị, ~113 s cho 5 nhóm trên 2 vCPU
(v0.3.4 rẻ hơn ~10 lần); trên VM 8 vCPU BurstGuard dùng tối đa 4 luồng
khi client đang rảnh (`burstguard.threads`).

---

## G. Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `ERROR (burstguard v0.3.4): the active virtual environment ... does not belong to this checkout` | `deactivate; cd ~/burstguard-v0.3.4 && source .venv/bin/activate` |
| `.venv was built for v0.1.1 but the code is v0.3.4` | `bash scripts/setup_venv.sh --recreate` |
| `dataset not found ... milan_d1.npz` | §C (tải + prepare, hoặc chép file từ VM khác) |
| `GuestbookNotFilled` / `... Guestbook response ...` | §C: `burstguard data guestbook`, điền file, chạy lại `data download` |
| `HTTP 401/403 from Dataverse ... datafile` | dùng API token của tài khoản Harvard Dataverse: `export DATAVERSE_API_TOKEN=...` (§C) |
| Job lỗi `BrokenProcessPool` / bị kill | Thiếu RAM: `--set engine.workers=2` hoặc sửa `engine.workers` trong `configs/base.toml` |
| BurstGuard loại cả vòng sạch | Ngưỡng thấp so với dữ liệu thật: chạy E0 + `burstguard calibrate`, cập nhật ngưỡng |
| Flower in cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 |

## H. Cách thủ công (không dùng `cluster.sh`)

### H.3 Ngày 1 — cài v0.3.4 trên cả 5 VM

Trên **vm-e** (đã có dữ liệu và mô hình):

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.4 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.4
cd ~/burstguard-v0.3.4 && bash scripts/setup_venv.sh && source .venv/bin/activate
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
cd ~/burstguard-v0.3.4
bash scripts/run_grids.sh k/5@4,1,3,1,3 --tier pilot,calibration,1,2    # trọng số = sức máy (vm-e, rồi thứ tự VM)
```

(`k` = 1, 2, 3, 4, 5 tương ứng từng VM; lệnh trên đặt trong `nohup bash -c '…' > logs/run.out 2>&1 &`, xem bằng `tail -f logs/run.out`.)

Khi P0 và E0 xong trên cả 5 VM (xem `logs/run_grids_*` có `END E0_calibration`), trên vm-e:

```bash
cd ~/burstguard-v0.3.4 && source .venv/bin/activate
bash scripts/sync_results.sh vm2 vm3 vm4 vm5     # kéo kết quả về (cần ssh từ vm-e sang các VM khác)
burstguard analyze all
burstguard calibrate experiments/E0_calibration.toml
burstguard plan
bash scripts/collect_logs.sh --campaign          # gửi mình .txt và .tar.gz
```

Mình cần từ pilot: ASR của 3 kiểu tấn công khi không lọc (head, LoRA), điểm BurstGuard của vòng sạch và vòng bị tấn công,
thời gian mỗi vòng. Nếu ASR quá thấp (backdoor không "ăn") hoặc BurstGuard báo nhầm, mình chỉnh độ mạnh tấn công/ngưỡng và
phát hành **v0.3.5** trước khi E3 chạy nhiều. Kết quả E1 không phụ thuộc các chỉnh này và sẽ được chép sang v0.3.5 (lệnh sẽ
có trong README của v0.3.5).

### H.5 Ngày 2–4 — chiến dịch chính

Lệnh ở H.4 đã gồm tầng 1 (E1 E2 E3 E7 E9) và tầng 2 (E4 E5 E6); bị ngắt thì chạy lại đúng lệnh đó.

Khi một VM xong sớm và đang rảnh: `bash scripts/run_grids.sh 1/1 --tier system` (E8 đo thời gian — chỉ chạy trên 1 VM).

Theo dõi:

```bash
burstguard plan                                     # còn bao nhiêu giờ (theo thời gian đo thật)
burstguard grid status experiments/E3_defenses.toml --shards 5
tail -n 3 logs/run_grids_v0.3.4_*.log
```

Mỗi tối (trên vm-e): `bash scripts/sync_results.sh vm2 vm3 vm4 vm5 && burstguard analyze all && bash scripts/collect_logs.sh --campaign`
và gửi mình file `.txt` — mình kiểm tra số liệu dở dang để phát hiện vấn đề sớm.

Bị ngắt (mất điện, khởi động lại)? Chạy lại **đúng lệnh** `run_grids.sh`: job xong được bỏ qua, job dở chạy lại.

### H.6 Ngày 5 — tổng hợp số liệu cho bài

```bash
bash scripts/sync_results.sh vm2 vm3 vm4 vm5
burstguard analyze all
burstguard paper                                    # -> results/v0.3.4/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign             # gửi mình cả .txt và .tar.gz
```

`results/v0.3.4/_paper/index.md` liệt kê artefact đã tạo và artefact còn thiếu (lưới chưa xong).

