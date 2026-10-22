# BurstGuard v0.3.3 — Chiến dịch thí nghiệm 7 ngày cho bài báo

> **v0.3.3 = v0.3.2 + chia việc theo sức máy (weighted shards):** máy mạnh nhận nhiều job hơn, máy yếu ít hơn;
> `cluster.sh import 0.3.2` chuyển các job đã xong ở v0.3.2 sang (không chạy lại); `burstguard plan` tính thời gian theo
> sức từng máy. Mã thí nghiệm giống hệt v0.3.0–v0.3.2 (kết quả gộp được, không cảnh báo lẫn phiên bản).
> (v0.3.2 = không cần tmux, `cluster.sh --bg collect`; v0.3.1 = `scripts/cluster.sh` điều khiển 5 VM qua ssh.)

> Dòng v0.3 = v0.2.2 + công cụ để ra đủ số liệu cho bài trong 7 ngày: lưới pilot `P0_pilot`, ước tính thời gian
> `burstguard plan`, chạy theo tầng ưu tiên `run_grids.sh --tier`, gom kết quả từ 5 VM `sync_results.sh`,
> `burstguard analyze all`, xuất bảng LaTeX/hình/số liệu cho bài `burstguard paper`, báo cáo `collect_logs.sh --campaign`.
> **BurstGuard: khi mô hình tổng hợp bị gắn cờ, không bỏ cả vòng nữa** mà gom lại các cập nhật của vòng đó thành
> 5 nhóm SecAgg ngẫu nhiên, sàng lọc từng nhóm và giữ các nhóm sạch (`burstguard.on_flag = regroup`, mặc định).
> Lý do: khi kẻ tấn công tham gia mọi vòng, “bỏ cả vòng” làm mô hình không học được gì (an toàn nhưng mất tác dụng);
> vòng sạch không phải lộ thêm thông tin nào. E7 có thêm 6 job so sánh với chính sách cũ (`on_flag = reject`).
> Thêm baseline phòng thủ `probe_screen` (từ chối mô hình tổng hợp nếu sai số trên dữ liệu probe công khai tăng > 5 % —
> cũng dùng được với SecAgg; trả lời câu hỏi “sao không kiểm tra bằng dữ liệu của server?”). E2 giảm còn 3 seed;
> E2/E3 lưu mô hình cuối (cho hình minh hoạ). Các tấn công giữ nguyên v0.2.x.

Chỉ README là tiếng Việt; toàn bộ log, thông báo lỗi và chú thích trong mã là tiếng Anh. Mọi file log/kết quả đều có
số phiên bản trong tên và trong nội dung.

---

## 1. Đã đủ viết bài chưa?

**Chưa.** Phần mềm và dữ liệu đã sẵn sàng, nhưng **chưa có con số thật nào** (mới chạy trên dữ liệu tổng hợp).

| Thành phần | Trạng thái (log v0.2.2, vm-e) |
|---|---|
| Dữ liệu Milan | ✅ 62 file (20,8 GB, 128 phút), `milan_d1.npz`: 20 site × 8928 khe, **0 khe thiếu**, không site nào có giá trị 0 |
| Mô hình TTM-R2 | ✅ `512-48-ft-r2.1`, 799.756 tham số; head 55K / decoder 247K / LoRA 107K / full 800K tham số huấn luyện |
| Pipeline, tấn công, phòng thủ, SecAgg+, phân tích | ✅ (kiểm thử trên dữ liệu tổng hợp) |
| Số liệu cho bài (E0–E9) | ❌ chưa chạy |
| Rủi ro chưa kiểm | backdoor có "ăn" vào TTM-R2 trên Milan không (ASR dưới FedAvg)? BurstGuard có báo động nhầm trên dữ liệu thật không? thời gian chạy thật? → **pilot P0 + E0 trả lời trong ~2 giờ** |

Bài cần (ánh xạ sang lưới thí nghiệm và artefact do `burstguard paper` tạo):

| Phần trong bài | Lưới | Artefact |
|---|---|---|
| Dataset | — | `tables/dataset.tex` |
| RQ1: FL có lợi so với local/zero-shot? Chi phí mỗi chế độ PEFT | E1 | `tables/clean.tex` |
| RQ2: mức độ dễ bị backdoor, tuổi thọ backdoor | E2, E5 | `tables/vulnerability.tex`, `figures/lifespan.pdf` |
| RQ3: phòng thủ hiện có vs BurstGuard; SecAgg theo nhóm; độ nhạy; tấn công thích nghi; ablation | E3, E7, E4, E6, E9 | `tables/defenses_{head,lora}.tex`, `figures/secagg_groups.pdf`, `figures/sensitivity.pdf`, `figures/burstguard_roc.pdf`, `tables/ablation.tex`, `figures/example_forecast.pdf` |
| RQ4: chi phí hệ thống | E8, E7 | `tables/system.tex`, `figures/screening_cost.pdf` |
| Số liệu trích trong văn bản | tất cả | `numbers.json` |

## 2. Kế hoạch 7 ngày (22/10 → 29/10)

Ước tính máy (giá trị mặc định trước khi đo, `burstguard plan --weights 4,1,3,1,3`): tầng 1 ≈ **52 giờ**, tầng 1 + 2
≈ **87 giờ** khi chia việc theo sức máy (xem “Sửa trong v0.3.3”); tính lại bằng số đo thật sau pilot.
Sau pilot, `burstguard plan` tính lại bằng thời gian đo thật.

| Ngày | Việc | Bạn làm | Gửi mình |
|---|---|---|---|
| **1 — Thứ Năm 22/10 (chiều/tối)** | Cài v0.3.3 trên 5 VM; chạy **P0_pilot + E0_calibration** (~1–2 h), rồi **E1_clean** (không phụ thuộc tinh chỉnh) | §3, §4 | `collect_logs.sh --campaign` sau P0+E0 |
| 1 (tối) | Mình phân tích pilot: độ mạnh tấn công, ngưỡng BurstGuard, thời gian → báo "giữ v0.3.3" hoặc phát hành v0.3.3 | — | — |
| **2–4 — 23/10 → 25/10** | Tầng 1: E2, E3, E7, E9 (E1 tiếp tục nếu chưa xong) → tầng 2: E4, E5, E6 → E8 trên 1 VM | §5 | mỗi tối 1 lần `--campaign` (để bắt lỗi sớm) |
| **5 — Thứ Hai 26/10** | Gom kết quả, `analyze all`, `paper` | §6 | `--campaign` (.txt + .tar.gz) |
| 5–6 | Mình viết phần Results/Discussion, hình, bảng; chạy bổ sung nếu thiếu | — | — |
| **7 — 28/10** + dự phòng 29/10 | Hoàn thiện bản thảo | — | — |

Nguyên tắc để kịp hạn: **tầng 1 trước, tầng 2 sau**; nếu trễ, cắt tầng 2 (E4/E6 → giảm còn 1 seed), không cắt tầng 1.

## Sửa trong v0.3.3 (so với v0.3.2)

**Vấn đề:** 5 máy không bằng nhau (theo log `cluster.sh check` ngày 22/10):

| Máy | Shard | CPU | RAM trống | Số worker chạy song song (= trọng số) |
|---|---|---|---|---|
| vm-e | 1 | 8 | 8,4 GB | 4 |
| vm-d (192.168.107.153) | 2 | 2 | 7,0 GB | 1 |
| vm-b (192.168.107.152) | 3 | 4 | 6,9 GB | 3 |
| vm-a (192.168.107.151) | 4 | 2 | 3,0 GB | 1 |
| vm-c (192.168.107.150) | 5 | 4 | 6,7 GB | 3 |

Số worker = công thức engine dùng khi chạy: `min(CPU − 1, (RAM trống − 2,5 GB) / 1,4 GB)`, tối thiểu 1.
Ở v0.3.2 mỗi máy nhận **cùng một lượng việc** (chia vòng tròn) → máy 1 worker (vm-d, vm-a) chạy chậm gấp ~4 lần vm-e
và quyết định thời gian của cả chiến dịch; vm-e xong sớm rồi ngồi chờ.

**Sửa:** `cluster.sh start` tính trọng số **một lần** (lần start đầu tiên của v0.3.3), lưu ở
`~/burstguard-shared/cluster.weights` (ví dụ `4,1,3,1,3`: vm-e trước, rồi theo thứ tự `cluster.hosts`) và giao việc
theo tỉ lệ đó: mỗi job (từ job nặng nhất) đi về máy có *(việc đã nhận + job)/trọng số* nhỏ nhất. Việc chia là cố định
và tất định — chạy lại `start` cho đúng cùng phân công.

**Hiệu quả ước tính** (`burstguard plan --weights 4,1,3,1,3`, thời gian mặc định trước khi đo): tầng 1 + tầng 2
≈ **87 giờ** chia theo sức máy, so với ≈ **194 giờ** nếu chia đều trên chính 5 máy này. (Ước tính “52 giờ” trước đây
giả định cả 5 máy mạnh như vm-e — tổng sức thật là 12 worker chứ không phải 20.) Thời gian sẽ được tính lại bằng số
đo thật sau pilot; nếu vẫn quá 3 ngày, mình sẽ đề xuất cắt bớt tầng 2.

Lưu ý:
- **Không sửa/xoá `cluster.weights` giữa chiến dịch** (nó quyết định máy nào chạy job nào). Chỉ xoá khi bắt đầu
  chiến dịch mới; lần `start` sau sẽ tính lại. Muốn chia đều như cũ: `cluster.sh --equal start ...`.
- Trọng số chỉ tính được khi **không** có thí nghiệm nào đang chạy (RAM trống sẽ bị đo thấp) — nếu còn chạy,
  `start` báo lỗi và yêu cầu `stop` trước.
- `cluster.sh status` in trọng số đang dùng; `burstguard plan` tự đọc file trọng số.

## Chuyển từ v0.3.2 khi đang chạy

Cứ để v0.3.2 chạy xong P0 + E0 (và `--bg collect` gửi báo cáo cho mình); E1 có thể đang chạy dở — không sao.
Khi mình xác nhận chạy tầng 1, làm **trên vm-e** theo đúng thứ tự:

```bash
# 1) cài v0.3.3 trên vm-e (song song với v0.3.2, không đụng v0.3.2)
deactivate 2>/dev/null
git clone -b release/v0.3.3 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.3
cd ~/burstguard-v0.3.3 && bash scripts/setup_venv.sh && source .venv/bin/activate && burstguard smoke

# 2) cài v0.3.3 trên 4 VM còn lại (cluster.hosts, khoá ssh, dữ liệu, mô hình dùng lại)
bash scripts/cluster.sh install && bash scripts/cluster.sh smoke

# 3) dừng lần chạy v0.3.2 trên cả 5 máy (phải gọi từ thư mục v0.3.2; job đang dở sẽ được chạy lại ở v0.3.3)
cd ~/burstguard-v0.3.2 && bash scripts/cluster.sh stop

# 4) chép các job đã xong ở v0.3.2 (P0, E0, phần E1 đã xong) sang v0.3.3 trên cả 5 máy -> không chạy lại
cd ~/burstguard-v0.3.3 && source .venv/bin/activate
bash scripts/cluster.sh import 0.3.2               # in số job đã chép trên từng máy

# 5) chạy tầng 1 + 2 với chia việc theo sức máy (lần đầu: tính và lưu ~/burstguard-shared/cluster.weights)
bash scripts/cluster.sh start "--tier 1,2"
bash scripts/cluster.sh status                     # dòng đầu in trọng số đang dùng
burstguard plan                                    # thời gian còn lại, tính theo sức từng máy
```

Phải **dừng (bước 3) trước khi import (bước 4)**: job nào v0.3.2 làm xong sau lúc import sẽ không được chép sang.
Kết quả E1 cũ có trong `~/burstguard-v0.3.2/results/v0.3.2/` vẫn giữ nguyên; xoá `~/burstguard-v0.3.2` sau khi
chiến dịch v0.3.3 xong và mình đã kiểm tra số liệu.

Theo dõi và gom kết quả như cũ (§5–6): `cluster.sh status`, `cluster.sh --bg collect <các lưới>`,
`burstguard paper`, `collect_logs.sh --campaign`.

## 3. Ngày 1 — cài đặt cả 5 VM (từng lệnh)

Mọi lệnh dưới đây chạy **trên vm-e** (VM đã có dữ liệu). vm-e là shard 1; 4 VM còn lại là shard 2–5.

### 3.1 Cài v0.3.3 trên vm-e

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.3 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.3
cd ~/burstguard-v0.3.3 && bash scripts/setup_venv.sh && source .venv/bin/activate
burstguard smoke                                   # phải ra 8 dòng [PASS]
rm -rf ~/burstguard-v0.3.1 ~/burstguard-v0.3.0 ~/burstguard-v0.2.2 ~/burstguard-v0.2.1   # bản cũ chưa có kết quả thí nghiệm
```

### 3.2 Khai báo 4 VM còn lại

Lấy địa chỉ IP của từng VM: đăng nhập vào VM đó (như bạn vẫn làm) và chạy `hostname -I` (lấy địa chỉ đầu tiên).
Trên vm-e kiểm tra đi tới được: `ping -c 1 <IP>`.

```bash
bash scripts/cluster.sh check                      # lần đầu: tạo file mẫu ~/burstguard-shared/cluster.hosts rồi dừng
nano ~/burstguard-shared/cluster.hosts             # ghi 4 dòng, mỗi dòng một VM, ví dụ:
#   root@10.0.0.12
#   root@10.0.0.13
#   root@10.0.0.14
#   root@10.0.0.15
```

Thứ tự các dòng = thứ tự shard (dòng 1 → shard 2, …, dòng 4 → shard 5). **Không đổi thứ tự trong suốt chiến dịch.**

### 3.3 SSH không cần mật khẩu từ vm-e sang 4 VM

```bash
bash scripts/cluster.sh keys
```

- Tạo khoá `~/.ssh/id_ed25519` (nếu chưa có) và chạy `ssh-copy-id` cho từng VM: **gõ mật khẩu root của VM đó một lần**.
- Nếu VM không cho đăng nhập bằng mật khẩu (`Permission denied (publickey)`), script in ra **một dòng lệnh**
  `mkdir -p ~/.ssh … >> ~/.ssh/authorized_keys …` — dán dòng đó vào terminal **của VM đó** (đăng nhập theo cách bạn
  vẫn dùng), rồi chạy lại `bash scripts/cluster.sh keys`.
- Kết thúc phải là 4 dòng `<VM>: OK`.

```bash
bash scripts/cluster.sh check
```

Mỗi VM phải có `git=ok python3=ok rsync=ok curl=ok setsid=ok`. Thiếu công cụ nào thì trên VM đó:
`sudo apt-get install -y git rsync curl`.

### 3.4 Chép dữ liệu, cài đặt, kiểm tra cả 4 VM

```bash
bash scripts/cluster.sh push-data      # milan_d1.npz (~1 MB) + mô hình TTM-R2 (~3 MB) vào ~/burstguard-shared của mỗi VM
bash scripts/cluster.sh install        # clone release/v0.3.3 + setup_venv.sh trên 4 VM song song (~3–6 phút)
bash scripts/cluster.sh smoke          # ~2 phút; mỗi VM phải "smoke OK (8 PASS)"
bash scripts/cluster.sh check          # bây giờ mỗi VM có data=ok venv=ok
```

Lỗi ở bước nào thì log nằm ở `logs/cluster_<lệnh>_<VM>_<thời_gian>.log` trên vm-e; gửi mình kèm
`bash scripts/collect_logs.sh --last 3`.

## 4. Ngày 1 — pilot + hiệu chỉnh (rồi E1): 2 lệnh trên vm-e

```bash
cd ~/burstguard-v0.3.3 && source .venv/bin/activate

# (a) khởi động cả 5 máy: vm-e = shard 1, 4 máy trong cluster.hosts = shard 2..5
bash scripts/cluster.sh start "--tier pilot,calibration" "E1_clean"

# (b) bước 6 tự động, chạy nền trên vm-e: chờ P0 + E0 xong ở cả 5 máy (kiểm tra 10 phút/lần),
#     rồi gom kết quả, analyze all, calibrate, plan, collect_logs --campaign
bash scripts/cluster.sh --bg collect P0_pilot E0_calibration
```

Mỗi máy chạy lần lượt `run_grids.sh k/5 --tier pilot,calibration` rồi `run_grids.sh k/5 E1_clean` ở chế độ nền
(`nohup`): thoát SSH, tắt máy tính của bạn đều không sao. Không cần đăng nhập vào từng máy.

Theo dõi (trên vm-e):

```bash
bash scripts/cluster.sh status                       # cả 5 máy: RUNNING?, dòng START/END gần nhất, số job ok/failed
tail -f logs/cluster_bg.out                          # xem trực tiếp shard của vm-e (Ctrl-C chỉ dừng việc xem)
tail -f $(ls -t logs/cluster_collect_*.log | head -1) # xem bước (b)
```

Khi bước (b) in `DONE` (khoảng 1–2 giờ), gửi mình **2 file mới nhất trong `~/burstguard-v0.3.3/reports/`**
(`.txt` và `.tar.gz`). E1 vẫn tiếp tục chạy trong lúc mình phân tích. Mình sẽ báo: giữ v0.3.3 hay phát hành bản chỉnh
(độ mạnh tấn công, ngưỡng BurstGuard). Kết quả E1 không phụ thuộc các chỉnh này.

Muốn làm bước 6 bằng tay thay vì (b): `bash scripts/sync_results.sh && burstguard analyze all &&
burstguard calibrate experiments/E0_calibration.toml && burstguard plan && bash scripts/collect_logs.sh --campaign`.

## 5. Ngày 2–4 — chiến dịch chính (trên vm-e)

Sau khi mình xác nhận:

```bash
bash scripts/cluster.sh stop                   # dừng E1 nếu còn chạy (job dở sẽ chạy lại)
bash scripts/cluster.sh start "--tier 1,2"     # tầng 1 (E1 E2 E3 E7 E9) rồi tầng 2 (E4 E5 E6), mỗi máy một shard
```

(Đang chạy v0.3.2? Làm theo “Chuyển từ v0.3.2 khi đang chạy” ở trên thay cho 2 lệnh này.)
Việc được chia theo sức máy (`~/burstguard-shared/cluster.weights`, tính ở lần `start` đầu tiên).

Khi `status` cho thấy vm-e đã `ALL GRIDS OK`, chạy E8 (đo thời gian, chỉ trên vm-e):
`bash scripts/cluster.sh --local-only --name e8 start "--tier system"`.

Mỗi tối (trên vm-e), rồi gửi mình file `.txt` mới nhất trong `reports/`:

```bash
bash scripts/cluster.sh status
bash scripts/sync_results.sh && burstguard analyze all && burstguard plan && bash scripts/collect_logs.sh --campaign
```

Một VM khởi động lại / mất điện? Chạy lại `bash scripts/cluster.sh start "--tier 1,2"`: máy đang chạy được bỏ qua
(`'bg' is already running`), máy đã dừng chạy tiếp từ job dở.

## 6. Ngày 5 — tổng hợp số liệu cho bài (trên vm-e)

```bash
bash scripts/cluster.sh --bg collect E1_clean E2_attacks E3_defenses E7_secagg E9_ablation E4_sensitivity E5_lifespan E6_adaptive
# khi log in DONE:
burstguard paper                                    # -> results/v0.3.3/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign             # gửi mình cả .txt và .tar.gz
```

`results/v0.3.3/_paper/index.md` liệt kê artefact đã tạo và artefact còn thiếu (lưới chưa xong).

## 7. Danh sách lưới (v0.3.3)

| Lưới | Tầng | Nội dung | Job | Giờ-VM (ước tính) |
|---|---|---|---|---|
| `P0_pilot` | pilot | {head, LoRA} × {không, poison, scale, constrain} + scale mạnh hơn — BurstGuard monitor, 20 vòng, 1 seed | 10 | ~3 |
| `E0_calibration` | calibration | BurstGuard monitor trên huấn luyện sạch, 4 PEFT × 3 seed | 12 | ~5 |
| `E1_clean` | 1 | FL × 4 PEFT vs local-only vs centralized vs zero-shot | 39 | ~10 |
| `E2_attacks` | 1 | 4 kịch bản × 4 PEFT × 3 seed, FedAvg | 48 | ~13 |
| `E3_defenses` | 1 | {không + 3 tấn công} × 10 phòng thủ (gồm `probe_screen`) × {head, LoRA} | 228 | ~71 |
| `E7_secagg` | 1 | SecAgg theo nhóm {1,2,4,5,10} × {FedAvg, BurstGuard, Median} + BurstGuard `reject` | 84 | ~31 |
| `E9_ablation` | 1 | 12 biến thể BurstGuard × {không, scale, constrain} | 108 | ~25 |
| `E4_sensitivity` | 2 | số site độc {1,2,4} × biên độ {0,5;1;2} × 3 phòng thủ | 81 | ~32 |
| `E5_lifespan` | 2 | tấn công vòng 10–19 trong 50 vòng | 39 | ~25 |
| `E6_adaptive` | 2 | tấn công thích nghi, Neurotoxin, trigger ngoài vùng tìm kiếm | 48 | ~27 |
| `E8_system` | system | Flower + SecAgg+ thật, 5 vòng | 8 | ~1 |

---

# Phần tham khảo

## A. Cài đặt v0.3.3 song song với phiên bản cũ (không xung đột)

**Không** `git pull` vào thư mục của phiên bản cũ. Mỗi phiên bản nằm ở thư mục riêng:

```bash
git clone -b release/v0.3.3 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.3
cd ~/burstguard-v0.3.3
cat VERSION                          # 0.3.3
bash scripts/setup_venv.sh           # tạo ~/burstguard-v0.3.3/.venv (khoảng 3–6 phút)
source .venv/bin/activate
burstguard info                      # in phiên bản, thư mục dự án, thư mục dùng chung
```

Bố cục trên VM sau khi cài:

```
/root/burstguard/            v0.1.1 (giữ nguyên, .venv riêng, không bị đụng tới)
~/burstguard-v0.2.2/         v0.2.2 (xoá được sau khi cài v0.3.3)
~/burstguard-v0.3.3/         v0.3.3: .venv/ .tools/ .cache/ runs/ results/v0.3.3/ logs/ reports/
~/burstguard-shared/         DÙNG CHUNG cho mọi phiên bản:
    data/raw/milan/          62 file thô (~20,8 GB) — chỉ cần trên VM làm bước prepare
    data/processed/          milan_d1.npz (~1 MB; "d1" = định dạng dữ liệu 1), synthetic_d1.npz
    hf/                      cache trọng số TTM-R2 (~3 MB)
```

Các cơ chế chống xung đột:

| Rủi ro | Cách tránh |
|---|---|
| Chạy nhầm mã v0.3.3 bằng `.venv` của v0.1.1 (hoặc ngược lại) | `.venv/burstguard_version`; `burstguard` báo lỗi và dừng nếu môi trường đang kích hoạt không phải `.venv` của đúng thư mục này hoặc khác phiên bản |
| `git pull` đè mã đang chạy | Mỗi phiên bản một bản clone; nâng cấp = clone thư mục mới |
| Ghi đè kết quả | Kết quả theo phiên bản: `results/v0.3.3/…`; tên run/report có `v0.3.3` |
| Dữ liệu cũ khác định dạng | File đã xử lý mang số định dạng (`milan_d1.npz`); mã kiểm tra số này khi đọc |
| Cụm Ray của hai phiên bản | Engine `flower` luôn khởi tạo cụm Ray cục bộ mới (`address="local"`); engine `local` không dùng Ray |
| Tranh CPU khi chạy hai phiên bản cùng lúc | Mặc định `nice 10`, số worker tự giới hạn theo CPU/RAM; tốt nhất không chạy hai lưới cùng lúc trên một VM |

Chuyển từ v0.1.1: không cần di chuyển gì (v0.1.1 chưa tải dữ liệu thật). Chạy `burstguard model-download` một lần trong
v0.3.3 (3 MB). Muốn đổi vị trí thư mục dùng chung: `export BURSTGUARD_SHARED=/đường/dẫn` **trước** khi cài và mỗi lần chạy.

Gỡ v0.3.3: `rm -rf ~/burstguard-v0.3.3` (không ảnh hưởng v0.1.1 và dữ liệu dùng chung).

---

## B. Kiểm tra nhanh (mỗi VM)

```bash
cd ~/burstguard-v0.3.3 && source .venv/bin/activate
burstguard doctor            # PASS/WARN/FAIL; FAIL phải sửa
burstguard smoke             # ~1–2 phút: 8 bước gồm cả Flower + SecAgg+ thật
python -m pytest -q          # 22 bài kiểm thử (~1–2 phút)
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
| `attack.start_round` / `end_round` | 1 / 0 | cửa sổ tấn công (0 = đến hết) |
| `trigger.width` / `amplitude` | 3 / 1.0 | burst 30 phút, biên độ × độ lệch chuẩn của site |
| `defense.name` | `fedavg` | `fedavg`, `clip_noise`, `krum`, `multikrum`, `trimmed`, `median`, `flame`, `fltrust`, `lora_reset`, `burstguard` |
| `secagg.enabled` / `secagg.groups` | false / 1 | secure aggregation; nhóm > 1 = SecAgg theo nhóm |
| `burstguard.reference` | `both` | so với mô hình vừa chấp nhận (`threshold`) và mô hình gốc (`threshold_anchor`) |
| `burstguard.anchor_adaptive` | `true` | ngưỡng anchor bám theo độ trôi lành tính (median + k·MAD); `false` = ngưỡng cố định |
| `burstguard.mode` | `enforce` | `monitor` = chỉ chấm điểm, không loại (dùng để hiệu chỉnh) |

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

Tạo `reports/bg_report_v0.3.3_<host>_<thời_gian>.txt` (gửi file này) và `.tar.gz` (chỉ khi mình yêu cầu).
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
  {δ ≥ 0, w ≤ 6 khe cuối, ≤ 2σ} bằng projected sign-gradient ascent trên cửa sổ probe, đo độ thay đổi tương đối của dự báo
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
| `scale` + BurstGuard, 1 mô hình tổng hợp, `on_flag = regroup` (v0.3.3) | 0,808 | 0,000 | gắn cờ 8/8 vòng; mỗi vòng gom lại 5 nhóm, loại đúng 16/16 nhóm có site độc, 0/24 nhóm lành bị loại; mô hình vẫn học như khi sạch |
| `scale` (2 site độc hại) + FedAvg, không phòng thủ | 1,379 | 0,379 | — (ASR val tăng 0,008 → 0,383 qua 8 vòng) |

Điểm anchor tăng đều theo vòng trên huấn luyện lành tính → v0.3.3 dùng ngưỡng anchor thích nghi (`anchor_adaptive`).
Chi phí sàng lọc: ~21 s CPU/vòng cho 1 đơn vị, ~113 s cho 5 nhóm trên 2 vCPU; trên VM 8 vCPU BurstGuard dùng tối đa 4 luồng
khi client đang rảnh (`burstguard.threads`).

---

## G. Lỗi thường gặp

| Hiện tượng | Xử lý |
|---|---|
| `ERROR (burstguard v0.3.3): the active virtual environment ... does not belong to this checkout` | `deactivate; cd ~/burstguard-v0.3.3 && source .venv/bin/activate` |
| `.venv was built for v0.1.1 but the code is v0.3.3` | `bash scripts/setup_venv.sh --recreate` |
| `dataset not found ... milan_d1.npz` | §C (tải + prepare, hoặc chép file từ VM khác) |
| `GuestbookNotFilled` / `... Guestbook response ...` | §C: `burstguard data guestbook`, điền file, chạy lại `data download` |
| `HTTP 401/403 from Dataverse ... datafile` | dùng API token của tài khoản Harvard Dataverse: `export DATAVERSE_API_TOKEN=...` (§C) |
| Job lỗi `BrokenProcessPool` / bị kill | Thiếu RAM: `--set engine.workers=2` hoặc sửa `engine.workers` trong `configs/base.toml` |
| BurstGuard loại cả vòng sạch | Ngưỡng thấp so với dữ liệu thật: chạy E0 + `burstguard calibrate`, cập nhật ngưỡng |
| Flower in cảnh báo `run_simulation is deprecated` | Bình thường với Flower 1.41 |

## H. Cách thủ công (không dùng `cluster.sh`)

### H.3 Ngày 1 — cài v0.3.3 trên cả 5 VM

Trên **vm-e** (đã có dữ liệu và mô hình):

```bash
deactivate 2>/dev/null
git clone -b release/v0.3.3 https://github.com/lamnguyentt92/burstguard.git ~/burstguard-v0.3.3
cd ~/burstguard-v0.3.3 && bash scripts/setup_venv.sh && source .venv/bin/activate
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

### H.4 Ngày 1 — pilot + hiệu chỉnh (rồi E1)

Đánh số VM 1..5 (vm-e = 1). Trên VM thứ *k* (chạy nền bằng `nohup`):

```bash
cd ~/burstguard-v0.3.3
bash scripts/run_grids.sh k/5 --tier pilot,calibration && bash scripts/run_grids.sh k/5 E1_clean
```

(`k` = 1, 2, 3, 4, 5 tương ứng từng VM; lệnh trên đặt trong `nohup bash -c '…' > logs/run.out 2>&1 &`, xem bằng `tail -f logs/run.out`.)

Khi P0 và E0 xong trên cả 5 VM (xem `logs/run_grids_*` có `END E0_calibration`), trên vm-e:

```bash
cd ~/burstguard-v0.3.3 && source .venv/bin/activate
bash scripts/sync_results.sh vm2 vm3 vm4 vm5     # kéo kết quả về (cần ssh từ vm-e sang các VM khác)
burstguard analyze all
burstguard calibrate experiments/E0_calibration.toml
burstguard plan
bash scripts/collect_logs.sh --campaign          # gửi mình .txt và .tar.gz
```

Mình cần từ pilot: ASR của 3 kiểu tấn công khi không lọc (head, LoRA), điểm BurstGuard của vòng sạch và vòng bị tấn công,
thời gian mỗi vòng. Nếu ASR quá thấp (backdoor không "ăn") hoặc BurstGuard báo nhầm, mình chỉnh độ mạnh tấn công/ngưỡng và
phát hành **v0.3.3** trước khi chạy tầng 1. Kết quả E1 không phụ thuộc các chỉnh này và sẽ được chép sang v0.3.3 (lệnh sẽ
có trong README của v0.3.3).

### H.5 Ngày 2–4 — chiến dịch chính

Sau khi mình xác nhận phiên bản dùng cho chiến dịch, trên VM thứ *k*:

```bash
bash scripts/run_grids.sh k/5 --tier 1,2           # tầng 1 (E1 E2 E3 E7 E9) rồi tầng 2 (E4 E5 E6)
```

Khi một VM xong sớm và đang rảnh: `bash scripts/run_grids.sh 1/1 --tier system` (E8 đo thời gian — chỉ chạy trên 1 VM).

Theo dõi:

```bash
burstguard plan                                     # còn bao nhiêu giờ (theo thời gian đo thật)
burstguard grid status experiments/E3_defenses.toml --shards 5
tail -n 3 logs/run_grids_v0.3.3_*.log
```

Mỗi tối (trên vm-e): `bash scripts/sync_results.sh vm2 vm3 vm4 vm5 && burstguard analyze all && bash scripts/collect_logs.sh --campaign`
và gửi mình file `.txt` — mình kiểm tra số liệu dở dang để phát hiện vấn đề sớm.

Bị ngắt (mất điện, khởi động lại)? Chạy lại **đúng lệnh** `run_grids.sh`: job xong được bỏ qua, job dở chạy lại.

### H.6 Ngày 5 — tổng hợp số liệu cho bài

```bash
bash scripts/sync_results.sh vm2 vm3 vm4 vm5
burstguard analyze all
burstguard paper                                    # -> results/v0.3.3/_paper/{tables,figures}, numbers.json, index.md
bash scripts/collect_logs.sh --campaign             # gửi mình cả .txt và .tar.gz
```

`results/v0.3.3/_paper/index.md` liệt kê artefact đã tạo và artefact còn thiếu (lưới chưa xong).

