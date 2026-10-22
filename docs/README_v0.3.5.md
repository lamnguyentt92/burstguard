# BurstGuard v0.3.5 — Chiến dịch chính (thay v0.3.4, chưa chạy)

> **v0.3.5 = v0.3.4 sửa theo kết quả đầy đủ của pilot P0 (10/10 job, v0.3.2):**
> - kẻ tấn công trở về mức 0,2 / 5 epoch (mức "mạnh" 0,5 / 10 epoch của v0.3.4 không đáng);
> - thêm **kẻ tấn công kín đáo** (boost γ = 3) thay cho `constrain_scale` trong E3/E9, vì `constrain_scale` không cấy
>   được backdoor;
> - BurstGuard sàng lọc bằng **1 luồng** (nhiều luồng không nhanh hơn);
> - chia việc **theo loại job**: job head (chủ yếu tốn ở server) chạy nhanh như nhau trên mọi máy, nên máy yếu nhận
>   nhiều job head hơn.
>
> Ước tính **~26–35 giờ** cho cả chiến dịch (v0.3.4: ~51 giờ). **Bỏ qua v0.3.4**: đừng chạy nó; nếu đã clone thì xoá
> được `rm -rf ~/burstguard-v0.3.4`. Mã thí nghiệm mới (`EXPERIMENT_CODE = 0.3.5`): P0 và E0 chạy lại.

Chỉ README là tiếng Việt; toàn bộ log, thông báo lỗi và chú thích trong mã là tiếng Anh. Mọi file log/kết quả đều có
số phiên bản trong tên và trong nội dung (`v0.3.5`).

---

## 1. Pilot P0 đầy đủ (v0.3.2, 10/10 job) cho thấy gì

Báo cáo `bg_report_v0.3.2_vm-e_20261022-132612.txt` (1 seed, 20 vòng, BurstGuard chế độ *monitor*, test split).
ASR = dự báo trên cửa sổ có trigger nằm trong ±50 % của đích tấn công (0,3 × thực tế, rất chặt);
UPR_trig = tỉ lệ cửa sổ có trigger bị **dự báo thiếu** (< 80 % thực tế) — hậu quả vận hành (thiếu tài nguyên).

| Tấn công (2/20 site) | Head: ASR / UPR_trig / MASE | LoRA: ASR / UPR_trig / MASE | BurstGuard AUC (head / LoRA) |
|---|---|---|---|
| Không | 0 / 0,008 / 0,657 | 0 / 0,008 / 0,637 | — |
| Data poisoning (γ = 1) | 0,001 / 0,110 / 0,686 | 0,000 / 0,204 / 0,632 | 0,90 / 0,96 |
| Norm-constrained (chuẩn ≤ cập nhật lành) | 0 / 0,011 / 0,653 | 0 / 0,012 / 0,626 | 0,57 / 0,52 |
| Model replacement (γ = 10), mặc định 0,2 / 5 epoch | 0,050 / **0,630** / 0,953 (+45 %) | **0,334** / **0,935** / 0,797 (+25 %) | 1,00 / 1,00 |
| Model replacement, "mạnh" 0,5 / 10 epoch | 0,075 / 0,810 / 1,153 (+75 %) | 0,406 / 0,971 / 0,943 (+48 %) | — |

Kết luận:
1. **Kẻ tấn công "mạnh" không đáng:** chỉ thêm ít ASR (LoRA 0,33 → 0,41) nhưng phá MASE gấp đôi, và client độc chạy
   chậm 2–3 lần → v0.3.5 trở lại 0,2 / 5 epoch.
2. **Norm-constrained không cấy được backdoor** (UPR ≈ huấn luyện sạch). Giới hạn chuẩn bằng cập nhật lành là quá chặt
   khi chỉ 2/20 site độc → chỉ giữ ở E2 (để báo cáo), bỏ khỏi E3/E9.
3. **Model replacement cấy được nhưng lộ** (MASE +25–45 %): một kiểm tra sai số đơn giản (`probe_screen`) cũng bắt được →
   bài cần một **kẻ tấn công kín đáo**: boost γ = 3 thay vì n/m = 10 (thay thế một phần mô hình). P0 mới đo γ = 3 và
   γ = 5; E2 vẽ đường đánh đổi độ mạnh–độ kín (γ = 1, 3, 5, 10).
4. **BurstGuard tách rất rõ:** vòng sạch last ≤ 0,02, anchor ≤ 0,08; vòng bị tấn công anchor 0,6–1,05. Cả data poisoning
   (gần như vô hại, UPR 0,1–0,2) cũng thấy được qua điểm anchor (AUC 0,90–0,96).
5. **Thời gian:** vòng head mất 86–116 s trên **mọi** máy (huấn luyện client chỉ 0,16 s; còn lại là sàng lọc
   ~80–110 s). Sàng lọc với 3–4 luồng dùng 250–440 s CPU nhưng không nhanh hơn 1 luồng (75–84 s CPU) → v0.3.5 dùng
   1 luồng. LoRA: 12 s/client → phụ thuộc số worker của máy.

## 2. Thay đổi trong v0.3.5 (so với v0.3.4)

| Thay đổi | v0.3.4 | v0.3.5 |
|---|---|---|
| Kẻ tấn công mặc định | 0,5 / 10 epoch | **0,2 / 5 epoch** (như v0.3.3) |
| Tấn công thứ hai trong E3, E9 | `constrain_scale` | **kín đáo: `scale` với `attack.boost = 3`** |
| E2 | scale × 4 PEFT; poison, constrain × head/LoRA | + **γ = 3 và γ = 5** × head/LoRA (đường đánh đổi) |
| P0 | none, scale, constrain ×1, ×3 | **none, scale γ = 10, γ = 3, γ = 5** × {head, LoRA} |
| `neurotoxin`, `adaptive` (E6) | không boost / bị giới hạn chuẩn | **có boost** như `scale` (nếu không thì không cấy được, như P0 cho thấy) |
| Luồng sàng lọc BurstGuard | min(4, CPU − 1) | **1** (`burstguard.threads`) |
| Chia việc giữa 5 máy | theo tổng chi phí / trọng số | **chi phí server (như nhau mọi máy) + chi phí client (/ số worker)** |
| `burstguard plan` | 1 hệ số/vòng | mô hình 2 phần, đo từ `clients_wall_s_mean`, `workers` trong `result.json` |
| Bảng `vulnerability` | ASR, ΔMASE | **ASR, UPR_trig, MASE, ΔMASE** theo từng γ |

Giữ nguyên từ v0.3.4: 20 vòng; BurstGuard 32 cửa sổ × 8 bước × 1 khởi tạo (batch), ngưỡng 0,08 / 0,3; client độc chạy
trước; ablation quy tắc tính lại từ điểm đã ghi; `[[exclude]]` theo seed.

## 3. Chạy v0.3.5 — từng lệnh, tất cả trên vm-e

v0.3.2 đã dừng (bạn đã làm). Kiểm tra lại không còn gì chạy:

```bash
pgrep -af "burstguard grid run" || echo "vm-e: none"
for h in $(grep -v '^#' ~/burstguard-shared/cluster.hosts); do echo "== $h"; ssh $h 'pgrep -af "burstguard grid run" || echo none'; done
```

### Bước 1 — cài v0.3.5 trên vm-e

```bash
deactivate 2>/dev/null
rm -rf ~/burstguard-v0.3.4                   # chỉ nếu bạn đã clone v0.3.4 (chưa chạy gì)
git clone -b release/v0.3.5 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.5
cd ~/burstguard-v0.3.5
bash scripts/setup_venv.sh                   # ~3–6 phút
source .venv/bin/activate
burstguard smoke                             # 8 dòng [PASS] và "RUN OK"
```

### Bước 2 — cài trên 4 VM còn lại

```bash
bash scripts/cluster.sh install              # clone release/v0.3.5 + setup_venv.sh trên 4 VM song song
bash scripts/cluster.sh smoke                # mỗi VM: "smoke OK (8 PASS)"
```

(Nếu đã chạy `cluster.sh install` của v0.3.4: xoá bản đó trên 4 VM cho gọn —
`for h in $(grep -v '^#' ~/burstguard-shared/cluster.hosts); do ssh $h 'rm -rf ~/burstguard-v0.3.4'; done`.)

### Bước 3 — chạy toàn bộ chiến dịch và tự gom báo cáo pilot

```bash
bash scripts/cluster.sh start "--tier pilot,calibration,1,2"
bash scripts/cluster.sh status               # dòng đầu: weights 4,1,3,1,3
bash scripts/cluster.sh --bg collect P0_pilot E0_calibration
tail -f $(ls -t logs/cluster_collect_*.log | head -1)     # Ctrl-C chỉ dừng việc xem
```

Mỗi máy chạy nền lần lượt P0 → E0 → E1 E2 E3 E7 E9 → E4 E5 E6 trên phần việc của mình. Khi log của `collect` in
**DONE** (dự kiến **~2 giờ**), gửi mình 2 file mới nhất:

```bash
ls -t ~/burstguard-v0.3.5/reports/ | head -2      # .txt và .tar.gz
```

Tầng 1 vẫn chạy tiếp trong lúc mình phân tích (E1 trước, không phụ thuộc tấn công). Từ P0 mình chọn γ cho kẻ tấn công
kín đáo: nếu γ = 3 quá yếu thì phát hành v0.3.6 đổi sang γ = 5 **trước khi E3 bắt đầu** (E3 chạy sau P0 + E0 + E1 + E2,
tức sau khoảng 6–7 giờ); các job đã xong được giữ lại.

### Nếu có lỗi ở bước nào

| Bước | Log | Gửi mình |
|---|---|---|
| 1 (setup/smoke trên vm-e) | `logs/setup_v0.3.5_*.log`, `runs/*_smoke/` | `bash scripts/collect_logs.sh --setup` hoặc `bash scripts/collect_logs.sh --last 3` |
| 2 (install/smoke trên VM khác) | `logs/cluster_install_<VM>_*.log`, `logs/cluster_smoke_<VM>_*.log` trên vm-e | 2 file log đó |
| 3 (job lỗi) | `bash scripts/cluster.sh status` (số job failed) | `bash scripts/sync_results.sh && bash scripts/collect_logs.sh --grid <lưới>` → file `.txt` mới nhất |

## 4. Theo dõi — làm sao biết khi nào xong

```bash
cd ~/burstguard-v0.3.5 && source .venv/bin/activate
bash scripts/cluster.sh status              # mỗi máy: RUNNING/not running, dòng START/END gần nhất, số job ok/failed
bash scripts/sync_results.sh && burstguard plan    # số giờ còn lại theo thời gian đo thật
tail -f logs/cluster_bg.out                 # xem trực tiếp phần của vm-e
```

- Một máy xong phần của nó khi log có `ALL GRIDS OK (shard k/5...)` và `status` báo `not running`.
- Con số `running=` trên vm-e có thể gồm cả thư mục chép về từ máy khác lúc job còn chạy (dấu cũ, không phải tiến trình).
- Cả chiến dịch xong khi **cả 5 máy** như vậy. Dự kiến bắt đầu tối 22/10 → xong khoảng **tối 23/10 – trưa 24/10**.

Mỗi tối (để mình bắt lỗi sớm), trên vm-e, rồi gửi mình file `.txt` mới nhất trong `reports/`:

```bash
bash scripts/sync_results.sh && burstguard analyze all && burstguard plan && bash scripts/collect_logs.sh --campaign
```

Một VM khởi động lại / mất điện: chạy lại đúng lệnh `start` ở bước 3 — máy đang chạy được bỏ qua
(`'bg' is already running`), máy đã dừng chạy tiếp từ job dở.

## 5. Khi cả 5 máy xong

```bash
# E8: đo thời gian hệ thống (Flower + SecAgg+ thật), chỉ trên vm-e, ~1 giờ
bash scripts/cluster.sh --local-only --name e8 start "--tier system"
# gom tất cả và xuất bảng/hình cho bài
bash scripts/cluster.sh --bg collect E1_clean E2_attacks E3_defenses E7_secagg E9_ablation E4_sensitivity E5_lifespan E6_adaptive E8_system
# khi log in DONE:
burstguard paper                            # -> results/v0.3.5/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign     # gửi mình cả .txt và .tar.gz
```

## 6. Kế hoạch còn lại (22/10 → 29/10)

| Ngày | Việc | Bạn làm |
|---|---|---|
| **22/10 tối** | Cài v0.3.5, chạy chiến dịch; P0 + E0 xong sau ~2 giờ | §3; gửi báo cáo khi DONE |
| 22/10 đêm – 23/10 sáng | Mình phân tích P0/E0 (γ của kẻ tấn công kín đáo, ngưỡng, thời gian) → giữ v0.3.5 hoặc v0.3.6 | — |
| **23/10 → 24/10** | Tầng 1 rồi tầng 2 chạy liên tục | §4; gửi `--campaign` mỗi tối |
| **24/10** | E8 trên vm-e; gom kết quả, `burstguard paper`; chạy bổ sung nếu thiếu | §5 |
| **25/10 → 28/10** | Viết Results/Discussion, bảng, hình | — |
| 29/10 | Dự phòng, hoàn thiện bản thảo | — |

Nếu trễ: cắt tầng 2 trước (E6 LoRA, E4 seed 1), không cắt tầng 1.

## 7. Danh sách lưới (v0.3.5)

Giờ-VM = giờ trên một máy 4 worker như vm-e (ước tính trước khi đo; `burstguard plan` cập nhật bằng số đo thật).

| Lưới | Tầng | Nội dung | Job | Giờ-VM |
|---|---|---|---|---|
| `P0_pilot` | pilot | {head, LoRA} × {không, scale γ=10, γ=3, γ=5} — monitor, 1 seed | 8 | ~2,5 |
| `E0_calibration` | calibration | BurstGuard monitor trên huấn luyện sạch, 4 PEFT × 2 seed | 8 | ~2,4 |
| `E1_clean` | 1 | FL × 4 PEFT × 3 seed; local-only, centralized (head, LoRA) × 2 seed; zero-shot | 21 | ~9 |
| `E2_attacks` | 1 | scale γ=10 × 4 PEFT × 3 seed; poison, γ=3, γ=5, constrain × {head, LoRA} × 2 seed (tham chiếu sạch = E1) | 28 | ~9 |
| `E3_defenses` | 1 | {không, γ=10, γ=3} × 9 phòng thủ × head × 3 seed + × 8 phòng thủ × LoRA × 2 seed | 129 | ~29 |
| `E7_secagg` | 1 | SecAgg theo nhóm {1,2,4,5,10} × {FedAvg, BurstGuard, Median} + BurstGuard `reject`, 2 seed | 56 | ~7 |
| `E9_ablation` | 1 | 10 biến thể tìm kiếm × {không, γ=10, γ=3} × 2 seed (+ 3 quy tắc tính lại không cần chạy) | 60 | ~6 |
| `E4_sensitivity` | 2 | số site độc {1,2,4} × biên độ {0,5;1;2} × {FedAvg, FLAME, BurstGuard}, 2 seed | 54 | ~8 |
| `E5_lifespan` | 2 | tấn công vòng 6–15 trong 40 vòng, {head, LoRA} × 4 phòng thủ, 2 seed | 14 | ~10 |
| `E6_adaptive` | 2 | tấn công thích nghi, Neurotoxin (có boost), trigger ngoài vùng tìm kiếm; head 3 seed, LoRA 1 seed | 36 | ~9 |
| `E8_system` | system | Flower + SecAgg+ thật, 5 vòng, 1 máy | 8 | ~1 |
| **Tổng** (không kể E8) | | | **414** | **~91 ≈ 26 giờ trên 5 máy** |

Bài cần (ánh xạ sang lưới và artefact do `burstguard paper` tạo):

| Phần trong bài | Lưới | Artefact |
|---|---|---|
| Dataset | — | `tables/dataset.tex` |
| RQ1: FL có lợi so với local/zero-shot? Chi phí mỗi chế độ PEFT | E1 | `tables/clean.tex` |
| RQ2: mức độ dễ bị backdoor, đánh đổi độ mạnh–độ kín, tuổi thọ backdoor | E2 (+E1), E5 | `tables/vulnerability.tex`, `figures/lifespan.pdf` |
| RQ3: phòng thủ hiện có vs BurstGuard; SecAgg theo nhóm; độ nhạy; tấn công thích nghi; ablation | E3, E7, E4, E6, E9 | `tables/defenses_{head,lora}.tex`, `figures/secagg_groups.pdf`, `figures/sensitivity.pdf`, `figures/burstguard_roc.pdf`, `tables/ablation.tex`, `figures/example_forecast.pdf` |
| RQ4: chi phí hệ thống | E8, E7 | `tables/system.tex`, `figures/screening_cost.pdf` |
| Số liệu trích trong văn bản | tất cả | `numbers.json` |

---

# Phần tham khảo

## A. Cài đặt v0.3.5 song song với phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng:

```bash
git clone -b release/v0.3.5 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.5
cd ~/burstguard-v0.3.5
cat VERSION                          # 0.3.5
bash scripts/setup_venv.sh           # tạo ~/burstguard-v0.3.5/.venv (khoảng 3–6 phút)
source .venv/bin/activate
burstguard info                      # in phiên bản, thư mục dự án, thư mục dùng chung
```

Bố cục trên VM sau khi cài:

```
/root/burstguard/            v0.1.1 (giữ nguyên, .venv riêng, không bị đụng tới)
~/burstguard-v0.2.2/         v0.2.2 (xoá được sau khi cài v0.3.5)
~/burstguard-v0.3.5/         v0.3.5: .venv/ .tools/ .cache/ runs/ results/v0.3.5/ logs/ reports/
~/burstguard-shared/         DÙNG CHUNG cho mọi phiên bản:
    data/raw/milan/          62 file thô (~20,8 GB) — chỉ cần trên VM làm bước prepare
    data/processed/          milan_d1.npz (~1 MB; "d1" = định dạng dữ liệu 1), synthetic_d1.npz
    hf/                      cache trọng số TTM-R2 (~3 MB)
```

Các cơ chế chống xung đột:

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã v0.3.5 bằng `.venv` của v0.1.1 (hoặc ngược lại) | `.venv/burstguard_version`; `burstguard` báo lỗi và dừng nếu môi trường đang kích hoạt không phải `.venv` của đúng thư mục này hoặc khác phiên bản |
| `git pull` đè mã đang chạy | Mỗi phiên bản một bản clone; nâng cấp = clone thư mục mới |
| Ghi đè kết quả | Kết quả theo phiên bản: `results/v0.3.5/…`; tên run/report có `v0.3.5` |
| Dữ liệu cũ khác định dạng | File đã xử lý mang số định dạng (`milan_d1.npz`); mã kiểm tra số này khi đọc |
| Cụm Ray của hai phiên bản | Engine `flower` luôn khởi tạo cụm Ray cục bộ mới (`address="local"`); engine `local` không dùng Ray |
| Tranh CPU khi chạy hai phiên bản cùng lúc | Mặc định `nice 10`, số worker tự giới hạn theo CPU/RAM; tốt nhất không chạy hai lưới cùng lúc trên một VM |

Chuyển từ v0.1.1: không cần di chuyển gì (v0.1.1 chưa tải dữ liệu thật). Chạy `burstguard model-download` một lần trong
v0.3.5 (3 MB). Muốn đổi vị trí thư mục dùng chung: `export BURSTGUARD_SHARED=/đường/dẫn` **trước** khi cài và mỗi lần chạy.

Gỡ v0.3.5: `rm -rf ~/burstguard-v0.3.5` (không ảnh hưởng v0.1.1 và dữ liệu dùng chung).

---

## B. Kiểm tra nhanh (mỗi VM)

```bash
cd ~/burstguard-v0.3.5 && source .venv/bin/activate
burstguard doctor            # PASS/WARN/FAIL; FAIL phải sửa
burstguard smoke             # ~1–2 phút: 8 bước gồm cả Flower + SecAgg+ thật
python -m pytest -q          # 27 bài kiểm thử (~3–5 phút)
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
| `burstguard.threads` | 1 | số luồng khi sàng lọc (v0.3.5; nhiều luồng không nhanh hơn) |

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

Tạo `reports/bg_report_v0.3.5_<host>_<thời_gian>.txt` (gửi file này) và `.tar.gz` (chỉ khi mình yêu cầu).
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
| `scale` + BurstGuard, 1 mô hình tổng hợp, `on_flag = regroup` (v0.3.5) | 0,808 | 0,000 | gắn cờ 8/8 vòng; mỗi vòng gom lại 5 nhóm, loại đúng 16/16 nhóm có site độc, 0/24 nhóm lành bị loại; mô hình vẫn học như khi sạch |
| `scale` (2 site độc hại) + FedAvg, không phòng thủ | 1,379 | 0,379 | — (ASR val tăng 0,008 → 0,383 qua 8 vòng) |

Điểm anchor tăng đều theo vòng trên huấn luyện lành tính → từ v0.3.3 dùng ngưỡng anchor thích nghi (`anchor_adaptive`).
Chi phí sàng lọc (v0.3.3: 64 cửa sổ × 20 bước × 2 khởi tạo): ~21 s CPU/vòng cho 1 đơn vị, ~113 s cho 5 nhóm trên 2 vCPU
(từ v0.3.4 rẻ hơn ~10 lần); trên VM 8 vCPU BurstGuard dùng tối đa 4 luồng
khi client đang rảnh (`burstguard.threads`).

---

## G. Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `ERROR (burstguard v0.3.5): the active virtual environment ... does not belong to this checkout` | `deactivate; cd ~/burstguard-v0.3.5 && source .venv/bin/activate` |
| `.venv was built for v0.1.1 but the code is v0.3.5` | `bash scripts/setup_venv.sh --recreate` |
| `dataset not found ... milan_d1.npz` | §C (tải + prepare, hoặc chép file từ VM khác) |
| `GuestbookNotFilled` / `... Guestbook response ...` | §C: `burstguard data guestbook`, điền file, chạy lại `data download` |
| `HTTP 401/403 from Dataverse ... datafile` | dùng API token của tài khoản Harvard Dataverse: `export DATAVERSE_API_TOKEN=...` (§C) |
| Job lỗi `BrokenProcessPool` / bị kill | Thiếu RAM: `--set engine.workers=2` hoặc sửa `engine.workers` trong `configs/base.toml` |
| BurstGuard loại cả vòng sạch | Ngưỡng thấp so với dữ liệu thật: chạy E0 + `burstguard calibrate`, cập nhật ngưỡng |
| Flower in cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 |

## H. Cách thủ công (không dùng `cluster.sh`)

### H.3 Ngày 1 — cài v0.3.5 trên cả 5 VM

Trên **vm-e** (đã có dữ liệu và mô hình):

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.5 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.5
cd ~/burstguard-v0.3.5 && bash scripts/setup_venv.sh && source .venv/bin/activate
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
cd ~/burstguard-v0.3.5
bash scripts/run_grids.sh k/5@4,1,3,1,3 --tier pilot,calibration,1,2    # trọng số = số worker (vm-e, rồi thứ tự VM)
```

(`k` = 1, 2, 3, 4, 5 tương ứng từng VM; lệnh trên đặt trong `nohup bash -c '…' > logs/run.out 2>&1 &`, xem bằng `tail -f logs/run.out`.)

Khi P0 và E0 xong trên cả 5 VM (xem `logs/run_grids_*` có `END E0_calibration`), trên vm-e:

```bash
cd ~/burstguard-v0.3.5 && source .venv/bin/activate
bash scripts/sync_results.sh vm2 vm3 vm4 vm5     # kéo kết quả về (cần ssh từ vm-e sang các VM khác)
burstguard analyze all
burstguard calibrate experiments/E0_calibration.toml
burstguard plan
bash scripts/collect_logs.sh --campaign          # gửi mình .txt và .tar.gz
```

Mình cần từ pilot: ASR của 3 kiểu tấn công khi không lọc (head, LoRA), điểm BurstGuard của vòng sạch và vòng bị tấn công,
thời gian mỗi vòng. Nếu ASR quá thấp (backdoor không "ăn") hoặc BurstGuard báo nhầm, mình chỉnh độ mạnh tấn công/ngưỡng và
phát hành **v0.3.6** trước khi E3 chạy nhiều. Kết quả E1 không phụ thuộc các chỉnh này và sẽ được chép sang v0.3.6 (lệnh sẽ
có trong README của v0.3.6).

### H.5 Ngày 2–4 — chiến dịch chính

Lệnh ở H.4 đã gồm tầng 1 (E1 E2 E3 E7 E9) và tầng 2 (E4 E5 E6); bị ngắt thì chạy lại đúng lệnh đó.

Khi một VM xong sớm và đang rảnh: `bash scripts/run_grids.sh 1/1 --tier system` (E8 đo thời gian — chỉ chạy trên 1 VM).

Theo dõi:

```bash
burstguard plan                                     # còn bao nhiêu giờ (theo thời gian đo thật)
burstguard grid status experiments/E3_defenses.toml --shards 5
tail -n 3 logs/run_grids_v0.3.5_*.log
```

Mỗi tối (trên vm-e): `bash scripts/sync_results.sh vm2 vm3 vm4 vm5 && burstguard analyze all && bash scripts/collect_logs.sh --campaign`
và gửi mình file `.txt` — mình kiểm tra số liệu dở dang để phát hiện vấn đề sớm.

Bị ngắt (mất điện, khởi động lại)? Chạy lại **đúng lệnh** `run_grids.sh`: job xong được bỏ qua, job dở chạy lại.

### H.6 Ngày 5 — tổng hợp số liệu cho bài

```bash
bash scripts/sync_results.sh vm2 vm3 vm4 vm5
burstguard analyze all
burstguard paper                                    # -> results/v0.3.5/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign             # gửi mình cả .txt và .tar.gz
```

`results/v0.3.5/_paper/index.md` liệt kê artefact đã tạo và artefact còn thiếu (lưới chưa xong).

