# BurstGuard v0.3.9 — Hoàn thiện số liệu: SMS/cuộc gọi (X4, X5) và trigger ngoài cửa sổ (X6)

> **v0.3.9 = v0.3.8 (chưa chạy, được thay hẳn) + 3 sửa lỗi + lưới X6 + tự động hoá phần cuối chiến dịch.**
> `EXPERIMENT_CODE` vẫn là 0.3.5 và mặc định không đổi, nên mọi kết quả của v0.3.5–v0.3.7 vẫn dùng được và được
> gộp lại bằng `cluster.sh import`. Tổng cộng 40 job mới, khoảng **4 giờ trên 5 máy**. Chỉ cần **2 lệnh chạy nền**,
> chạy qua đêm được, không phải canh.

Chỉ README là tiếng Việt; log, thông báo lỗi và chú thích trong mã là tiếng Anh; mọi log/kết quả có `v0.3.9` trong tên.

---

## 1. Phân tích v0.3.7 (X3, 34/34 job OK)

| Cấu hình (W = cửa sổ BurstGuard tìm kiếm) | Offset 0 | Offset 12 |
|---|---|---|
| head, γ=10, W=6 | TPR 1,00 | TPR 0,73, UPR 0,22 (lỗ hổng cũ của E6) |
| head, γ=10, **W=18** | TPR 1,00 | **TPR 1,00, UPR 0,03** ✔ |
| LoRA, γ=3, **W=18** | — | **TPR 0,90, UPR 0,05** ✔ |
| head, γ=3, **W=18** | TPR 1,00 | **TPR 0,05, UPR 0,47** ✘ (còn lại 1 lỗ hổng) |
| không tấn công, W=18 | FPR 0, MASE không đổi | — |

Nguyên nhân lỗ hổng còn lại là **luật ngưỡng**, không phải thuật toán tìm kiếm. Điểm của vòng sạch và vòng bị tấn
công tách nhau rất rõ:

- **Điểm mỗi vòng (S_last):** vòng sạch ≤ 0,033, vòng tấn công 0,06–0,10. Ngưỡng 0,08 đặt cho W=6 nên với W=18
  lại quá lỏng.
- **Điểm tích luỹ so với mô hình gốc (S_anchor):** tăng đều 0,10 → 0,66 trong 20 vòng. Ngưỡng thích nghi
  (median + 5·MAD của các vòng đã nhận) "đi theo" đúng đường tăng chậm đó, nên không bao giờ gắn cờ (hiện tượng
  "luộc ếch").

## 2. Lỗi của v0.3.8 (chưa chạy) mà v0.3.9 sửa

Mình kiểm tra lại v0.3.8 trên dữ liệu thật của X3/E7 và thấy 3 lỗi, sẽ làm hỏng số liệu nếu chạy:

1. **Ngưỡng hiệu chỉnh quá sát cho bước regroup.** Ngưỡng hiệu chỉnh = 1,5 × điểm sạch lớn nhất *của toàn bộ
   aggregate*. Khi regroup, mỗi nhóm chỉ gồm ~4 máy nên điểm của nhóm sạch tự nhiên cao gấp 2,4–2,6 lần (đo từ E7,
   G=5). Hậu quả: nhóm sạch cũng bị loại và mô hình ngừng học khi có tấn công.
   → **Sửa:** khi regroup, ngưỡng của nhóm nhân √G (`burstguard.regroup_threshold_scale = "sqrt"`). Điểm của nhóm
   được đưa về thang của aggregate trước khi vào lịch sử ngưỡng. Mặc định vẫn là 1,0, nên kết quả cũ không đổi.
2. **Ngưỡng anchor thích nghi lấy từ các vòng đầu gây báo động giả trên LoRA.** Phát lại trên X3 ở W=6 cho 14 lần
   gắn cờ nhầm, và luật thích nghi còn để lọt kẻ tấn công tăng chậm.
   → **Sửa:** `calibrate --write-thresholds` mặc định ghi **anchor cố định** = 1,5 × điểm anchor sạch lớn nhất của
   cả 20 vòng. Phát lại trong mẫu cho 0 báo động giả.
3. **FPR đo trên chính các seed đã dùng để hiệu chỉnh** thì luôn bằng 0 (và chạy lại chỉ lặp X4).
   → **Sửa:** các job sạch của X5 và X6 dùng **seed chưa dùng để hiệu chỉnh**, nên FPR là số đo thật.

Ngoài ra:
- **X4 rút gọn còn 6 job sạch.** Các job tấn công ở chế độ monitor là thừa, vì X5 (enforce, đúng cách triển khai)
  cũng ghi điểm của mọi vòng.
- **Bỏ bước làm tay giữa X4 và X5:** X5 tự chờ file ngưỡng, còn `cluster.sh finish` tự hiệu chỉnh và chép file
  ngưỡng sang các máy.

## 3. Lưới chạy trong v0.3.9

| Lưới | Nội dung | Job |
|---|---|---|
| `X4_traffic_bg_monitor` (tier `traffic_bg`) | SMS/cuộc gọi, sạch, monitor, `rel_floor = 0,1`; head seed 0,1 + LoRA seed 0. Dùng để hiệu chỉnh ngưỡng | 6 |
| `X6_offset_calibrated` (tier `offset2`) | Internet, W=18, ngưỡng hiệu chỉnh từ X3 sạch (0,05 / 0,153, anchor cố định), regroup √G. Gồm offset 0/12 × γ=10/γ=3, head 3 seed; LoRA γ=3 offset 12; sạch: head seed 3,4 + LoRA seed 3 (giữ riêng) | 16 |
| `X5_traffic_bg_enforce` (tier `traffic_bg2`) | SMS/cuộc gọi, enforce, ngưỡng từ X4, regroup √G. Tấn công γ=10/γ=3 (head seed 0,1, LoRA seed 0); sạch: head seed 2,3 + LoRA seed 2 (giữ riêng) | 18 |

Mỗi máy chạy X4 → X6 → X5. X5 chờ file ngưỡng và ghi 1 dòng log mỗi 5 phút. `cluster.sh finish` (chạy nền trên
vm-e) làm phần còn lại:

1. đợi X4 xong trên cả 5 máy;
2. hiệu chỉnh SMS và cuộc gọi, ghi `~/burstguard-shared/bg_thresholds.toml` và chép sang 4 máy (X5 tự chạy, thường
   lúc này X6 vẫn đang chạy nên không mất thời gian chờ);
3. đợi mọi lưới xong;
4. `analyze all`, `bg-check`, `paper`, báo cáo chiến dịch.

Ngưỡng của X6 được tính bằng đúng quy trình hiệu chỉnh (`burstguard calibrate`) trên 4 job sạch W=18 của X3:
S_last sạch lớn nhất 0,0331, S_anchor 0,1022, margin 1,5, nên 0,05 / 0,153. Trên các điểm đã ghi của X3, kẻ tấn công
head γ=3 offset 12 có S_last 0,06–0,10 ngay từ vòng 1, đều > 0,05. Hai bảng `offset.tex` và `generalization.tex`
tự thêm các hàng mới (`W=18 cal.` từ X6; BurstGuard SMS/cuộc gọi từ X5). Hình `lifespan` có thêm hàng UPR_trig.

## 4. Lệnh chạy — tất cả trên vm-e

### Bước 1 — cài và kiểm thử v0.3.9 trên vm-e (~10 phút)

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.9 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.9
cd ~/burstguard-v0.3.9 && bash scripts/setup_venv.sh && source .venv/bin/activate
python -m pytest -q                   # tất cả passed (33 test)
burstguard smoke                      # 8 dòng [PASS], RUN OK
```

### Bước 2 — cài trên 4 VM còn lại, gộp kết quả cũ (~10 phút)

```bash
bash scripts/cluster.sh install && bash scripts/cluster.sh smoke     # 4 máy: setup OK, smoke OK
for v in 0.3.5 0.3.6 0.3.7; do bash scripts/cluster.sh import $v; done
```

Mỗi dòng của `import` in ra `imported N finished jobs ...` cho từng máy.

### Bước 3 — chạy (2 lệnh nền, rồi có thể đăng xuất)

```bash
bash scripts/cluster.sh start "--wait-idle --tier traffic_bg,offset2,traffic_bg2"
bash scripts/cluster.sh --bg finish
```

Theo dõi (Ctrl-C chỉ thoát `tail`, không dừng gì):

```bash
tail -f $(ls -t logs/cluster_finish_*.log | head -1)    # "step 1/2 ... X4 not finished yet: k/6" -> "thresholds for ..." -> "step 2/2"
bash scripts/cluster.sh status                           # tiến độ từng máy
```

Khi log `finish` in `DONE - send the two newest files ...` là xong toàn bộ (khoảng 4–5 giờ).

### Bước 4 — gửi mình kết quả

```bash
ls -t ~/burstguard-v0.3.9/reports/ | head -2      # bg_report_v0.3.9_vm-e_<thời gian>.txt và .tar.gz
```

Gửi mình **cả 2 file** (.txt và .tar.gz). Trong đó có: mọi bảng/hình của bài, `numbers.json`, file ngưỡng đã hiệu
chỉnh, kết quả `bg-check` và phân tích từng lưới.

## 5. Nếu có lỗi

| Tình huống | Làm gì / gửi mình |
|---|---|
| Bước 1 (setup / pytest / smoke) lỗi | toàn bộ màn hình lỗi + `bash scripts/collect_logs.sh --setup` |
| `install` / `smoke` / `import` / `start` báo lỗi một máy | màn hình lỗi + các file `logs/cluster_<lệnh>_<máy>_*.log` |
| Log `finish` báo `ERROR: calibration of sms/call failed` | `logs/finish_calibrate_sms.log`, `logs/finish_calibrate_call.log` + `bash scripts/collect_logs.sh --grid X4_traffic_bg_monitor` |
| Log `finish` báo `WARNING: push-data had errors` | chạy `bash scripts/cluster.sh push-data`; X5 trên máy đó tự chạy ở lần kiểm tra sau (≤ 5 phút) |
| Có job lỗi (`status` hiện `failed=`) | `bash scripts/sync_results.sh && bash scripts/collect_logs.sh --grid X5_traffic_bg_enforce` (hoặc X4/X6) |
| Máy bị khởi động lại / mất ssh | chạy lại đúng 2 lệnh của Bước 3: job đã xong được bỏ qua, job dở dang chạy lại |
| `finish` đã dừng (vm-e khởi động lại) | `bash scripts/cluster.sh --bg finish` (chạy lại an toàn: hiệu chỉnh lại ra cùng ngưỡng) |
| Không chắc đang ở bước nào | `bash scripts/cluster.sh status` + 30 dòng cuối của `logs/cluster_finish_*.log` |

Cách lấy output bằng tay, khi thành công hay thất bại:

```bash
cd ~/burstguard-v0.3.9 && source .venv/bin/activate
bash scripts/sync_results.sh                       # kéo kết quả từ 4 máy về vm-e
bash scripts/collect_logs.sh --campaign            # thành công: báo cáo đầy đủ -> reports/
bash scripts/collect_logs.sh --failed              # thất bại: mọi run lỗi trên vm-e
bash scripts/collect_logs.sh --grid X5_traffic_bg_enforce   # một lưới (X4_..., X6_...)
```

---

# Phần tham khảo

## A. Cài v0.3.9 song song với các phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng `~/burstguard-v0.3.9`, có
`.venv`, `results/v0.3.9/`, `logs/`, `reports/` riêng. Dữ liệu và trọng số mô hình dùng chung ở `~/burstguard-shared/`.

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã bằng `.venv` của phiên bản khác | `.venv/burstguard_version`: `burstguard` dừng nếu môi trường đang kích hoạt không thuộc thư mục này |
| `git pull` đè mã đang chạy | mỗi phiên bản một bản clone |
| Ghi đè kết quả | kết quả theo phiên bản: `results/v0.3.9/...`; tên run/log/report có `v0.3.9` |
| Hai phiên bản dùng chung CPU | `--wait-idle`: mỗi máy chờ phiên bản cũ (nếu còn chạy nền) xong rồi mới bắt đầu |
| File ngưỡng cũ | `bg_thresholds.toml` chỉ được ghi bởi `calibrate`. v0.3.8 chưa chạy nên chưa có file này. Chạy lại `finish` sẽ ghi đè bằng đúng giá trị mới |

## B. Thay đổi trong mã (chi tiết: CHANGELOG.md)

- `burstguard.regroup_threshold_scale`: số ≥ 1 hoặc `"sqrt"` (= √G). Mặc định 1,0, giữ nguyên hành vi v0.3.5.
- `burstguard calibrate --anchor fixed|adaptive`: mặc định `fixed`. `--where KEY=VALUE` khớp cả với giá trị trong
  `config.toml` của job (vd. `data.path` khi lưới không thay đổi nó).
- `burstguard grid run` chờ file ngưỡng còn thiếu (`burstguard.threshold_file`). Có thể chỉnh bằng
  `BURSTGUARD_WAIT_POLL_S` (mặc định 300 giây) và `BURSTGUARD_WAIT_INPUTS_H` (48 giờ); `--no-wait` để không chờ.
- `cluster.sh finish`; `collect` có thể chạy `bg-check` + `paper`. Báo cáo `--campaign` có file ngưỡng, `bg-check`
  và 10 run gần nhất.
- Phân tích: `lifespan_upr_l50` (thời gian sống của backdoor tính theo UPR_trig). Hình `lifespan` có 2 hàng
  (ASR, UPR_trig). Bảng `offset.tex` có hàng `W=18 cal.`.

## C. Kiểm tra lại ngưỡng của X6 (tuỳ chọn, sau Bước 2)

```bash
burstguard calibrate experiments/X3_trigger_offset.toml --where burstguard.width_max=18 --where attack.type=none
```

Mục `"suggested, fixed anchor (1.5x clean max)"` phải cho `threshold 0.05`, `threshold_anchor 0.153`,
`replayed_fpr_units 0.0`.
