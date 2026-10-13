# Gói phục hồi và chuyển phần native/PPO sang máy khác

Source đã commit ở `2bc259e`, branch `codex/active-sensing-integration`. Các gói dưới đây nằm ngoài Git tại `P-027-local-rescue-20261013`, không chứa `.env`, credential hoặc runtime Linux/Windows cũ.

| File | Nội dung | Kiểm tra |
| --- | --- | --- |
| `mvp-native-ready-2bc259e.bundle` | Source/history Git | `git bundle verify` thành công |
| `native-mvp-ready-2bc259e-data.zip` | SQLite snapshot nhất quán, capture PNG/NPZ/geometry, predictions, catalogs | 870 member; CRC và SHA đã kiểm tra |
| `native-rl-model-assets-2bc259e.zip` | 7 checkpoint project + manifest; PPO policy được chọn, report và seal | CRC, từng checkpoint SHA, policy/report SHA; giải nén mới đã kiểm tra service đọc được |

Đây là gói cho **native preview và PPO evidence**. Toàn bộ Lab nuScenes vẫn cần dataset/cache/exports đang có của team; không gọi hai ZIP này là toàn bộ nuScenes. Không copy virtual environment hoặc `node_modules` giữa Windows/Linux.

## Restore source và assets

Clone bundle vào folder mới, không ghi đè repo đang chạy:

```bash
git clone -b codex/active-sensing-integration /path/mvp-native-ready-2bc259e.bundle P-027-restored
cd P-027-restored
```

Giải nén cả hai ZIP vào root repo mới. Khi đó có `data/experiments`, `data/rl-occupancy-ppo-20261013` và `lab/models`. Giữ các file `.sha256` và đối chiếu SHA archive trước khi giải nén. Không lấy backup source/runtime đã biết hỏng để ghi đè bản mới.

Thiết lập các đường dẫn theo máy đích:

```dotenv
LAB_DATA_ROOT=/absolute/path/P-027-restored/lab
EXPERIMENT_ROOT=/absolute/path/P-027-restored/data/experiments
OCCUPANCY_RL_ROOT=/absolute/path/P-027-restored/data/rl-occupancy-ppo-20261013
```

Các report pilot và input-adapter manifest mặc định nằm trong `eval/recovery-mvp-2026-10-13` của source. Restore không tự thay checkpoint hoặc tự admit dữ liệu native cho RL. SQLite trong ZIP là snapshot đã hoàn tất, không chuyển một job running dở thành succeeded.

Cài dependencies theo README cho nền tảng đích rồi build frontend. Runtime phục hồi riêng của máy hiện tại không nằm trong gói. Nếu dùng script `run_local_mvp.sh`, cần đúng Python/Node runtime được script ghi rõ; đây là launcher cho máy phục hồi, không là installer đa nền tảng.

## Giới hạn deploy

- Server có thể đọc evidence/capture đã tính sẵn khi có assets và cấu hình truy cập đúng. CARLA live cần Linux GPU, runtime/client tương thích, worker và RAM; GitHub/Vercel/Supabase không tự cung cấp các thành phần đó.
- Production experiments vẫn opt-in theo guard hiện có. Không bỏ auth/guard chỉ để mở demo; team cấu hình theo môi trường deploy.
- Dữ liệu native nằm ngoài Git nên auto-deploy source không tự chuyển SQLite/capture/weights/policy. Team phải chuyển các gói assets riêng.
- Đường dẫn raw nuScenes và cache/exports của deployment cũ vẫn phải được kiểm tra riêng. Không sử dụng connection string database như địa chỉ backend.

Evidence kiểm tra gói: `eval/recovery-mvp-2026-10-13/portable-assets-check.json`. Bộ đầy đủ của repo phục hồi hiện **245 test passed**, TypeScript/ESLint và production build đã qua. Browser QA bản cuối vẫn cần mở tab Lab hợp lệ; HTTP 200 không thay thế kiểm tra thao tác UI.
