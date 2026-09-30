# Triển khai demo và Runner của đội

## Phân công và phương án ưu tiên
Người 1 phụ trách CI, tích hợp Docker/Compose, gateway, tunnel, URL HTTPS, tài khoản demo và rollback. Người 3 phụ trách backend, dependency, Dockerfile backend, data paths, healthcheck và hỗ trợ lỗi API. Benchmark/report và camera panel thuộc người 3; người 1 chỉ tích hợp vào routing. Người 2 phụ trách viewer/compare và kiểm tra hiệu năng.

Ưu tiên demo tiết kiệm bằng máy đội chạy Docker + Cloudflare Tunnel. Chưa cần thuê VPS. Người 1 cần bổ sung cấu hình gateway local/tunnel; compose hiện có bên dưới vẫn là phương án VPS/domain, không chạy nguyên trạng như cấu hình tunnel. Không bỏ đăng nhập hoặc mở đường static tới camera gốc khi đổi gateway. Máy demo phải bật, không sleep và có mạng; kiểm tra URL bằng máy ngoài mạng. Quick Tunnel có URL tạm thời; cần URL cố định thì chuẩn bị tên miền/tunnel phù hợp. Chưa triển khai tunnel hoặc mở ứng dụng ra Internet trong lần cập nhật tài liệu này.

## Runner có dùng cho việc này không?
Có, ở khâu CI/CD. Runner nhận job GitHub Actions để test, build và chạy lệnh deploy. Nó không tự tạo website, IP công khai, tên miền hay HTTPS. Laptop tắt thì runner offline; nếu ứng dụng demo cũng chạy trên laptop đó thì website cũng ngừng truy cập. Website trên VPS độc lập không phụ thuộc laptop.

Luồng đề xuất:
Developer -> PR -> CI trên runner/pool -> merge main -> deploy bản đã kiểm thử -> máy đội chạy Docker + gateway + Cloudflare Tunnel -> giám khảo. VPS là phương án thay thế nếu cần hoạt động liên tục.

Thông tin Phoenix về token/quyền đội trưởng dựa trên mô tả người dùng cung cấp; chưa truy cập hay đăng ký runner trong Phoenix.

## VPS dự phòng nếu cần hoạt động liên tục
Điểm bắt đầu để thử tải: Linux x86_64, 4 vCPU, RAM 8 GB, SSD 40–60 GB, IP công khai; không cần GPU cho detection/benchmark tính sẵn. Đây là ước lượng kỹ thuật, chưa phải cấu hình đã benchmark. Nếu chỉ dùng artifact demo nhỏ có thể giảm sau đo tải. Build Next và xử lý ảnh có thể cần RAM nhiều hơn phục vụ bình thường.

Raw mini khoảng 5.06 GiB; chừa chỗ Docker images, build cache, media và rollback. Không thuê GPU chỉ để hiển thị CSV. Suy luận BEVFusion/CRN ở Kaggle hoặc GPU worker riêng; occupancy/flow CPU là tính năng bổ sung sau khi đo hiệu năng.

## Cấu hình đã chuẩn bị
- Dockerfile backend dùng Python 3.12, chạy non-root, không phụ thuộc /root/.local.
- frontend/Dockerfile dùng standalone Next.js.
- deploy/compose.yml: backend + frontend ở mạng nội bộ; chỉ Caddy mở 80/443.
- Caddy tự cấp HTTPS cho domain trỏ đúng server; toàn site có Basic Auth cho giám khảo.
- Data bind mount read-only ngoài image tại LAB_VOLUME.
- Anonymizer mặc định tắt: camera API trả 503 thay vì ảnh gốc. Image inference dependencies/weights chưa có trong image web.
- /lab/* static legacy bị chặn ở gateway vì ảnh composite camera chưa có audit anonymization. Runtime image frontend hiện không copy public/lab, tránh cả đường Next image optimizer. Chỉ copy simulation media và SVG skeleton; UI team bổ sung asset đã duyệt vào Dockerfile khi cần.
- UI hiện skeleton. Deploy cấu hình này chưa biến skeleton thành lab hoàn chỉnh.

## Cài đặt lần đầu trên VPS
1. Cài Docker Engine + Compose plugin theo tài liệu chính thức cho hệ điều hành của VPS.
2. Clone repo bằng tài khoản/deploy key được cấp quyền. Checkout commit đã CI xanh.
3. Đặt data/lab, data/sim và nuScenes cần dùng dưới /srv/p027/data. Không đưa raw dataset vào Docker image hay Git.
4. Copy deploy/.env.example thành deploy/.env (không commit), điền LAB_DOMAIN và LAB_VOLUME.
5. Tạo hash mật khẩu bằng lệnh tương tác, không lưu plaintext vào workflow:
   docker run --rm -it caddy:2-alpine caddy hash-password
   Dán hash vào JUDGE_PASSWORD_HASH trong dấu nháy đơn.
6. Trỏ DNS domain về IP VPS; mở TCP 80/443. Hạn chế SSH theo tài khoản quản trị.
7. Từ repo root:
   docker compose --env-file deploy/.env -f deploy/compose.yml config --quiet
   docker compose --env-file deploy/.env -f deploy/compose.yml up -d --build
   docker compose --env-file deploy/.env -f deploy/compose.yml ps
8. Kiểm tra bằng trình duyệt ngoài mạng local: HTTPS, đăng nhập, /health, /api/v1/lab/capabilities và thao tác UI.
9. Ghi commit SHA đang chạy; giữ checkout/release trước. Rollback bằng checkout release đã kiểm thử rồi build/up lại; không xóa data volume.

Đây là hướng dẫn và cấu hình chuẩn bị, chưa chạy production do chưa có server/domain. Đã build cả hai image Linux và smoke-test non-root: backend đọc 81 frame qua data mount chỉ đọc; frontend trả HTTP 200. Compose config và Caddy validate đều pass. Chưa kiểm tra DNS/cấp certificate thật hoặc tải nhiều người dùng trên VPS.

## Dùng runner Phoenix
- Đội trưởng lấy token trên trang Phoenix; chọn đúng OS/architecture và làm theo lệnh Phoenix hiển thị. Không paste token vào repo/chat/log.
- Đăng ký runner CI trên máy riêng hoặc VM, cài dưới dạng service nếu chạy 24/7.
- Runner đã đăng ký: team-27-Munfond; labels: self-hosted, Windows, X64, team-27.
- Workflow hiện dùng trực tiếp runs-on: [self-hosted, Windows, X64, team-27] cho backend và frontend; không cần tạo repository variable.
- Dùng shell powershell có sẵn trên Windows, không yêu cầu PowerShell 7/pwsh. setup-python/setup-node chuẩn bị runtime cho job.
- GitHub chọn máy khớp tất cả nhãn; runner offline thì job chờ, không tự fallback về pool chung.
- Với một runner, hai job có thể chạy lần lượt. Giữ run.cmd hoạt động và máy không sleep, hoặc cấu hình service theo hướng dẫn web Lab.
- Giữ runner chạy PR tách khỏi production data/secrets. Repo private vẫn có thể chạy code do collaborator sửa.
- Người 1 deploy ban đầu thủ công trên máy demo với tunnel; nếu chọn VPS thì dùng hướng dẫn trên. Khi URL hoạt động, thêm workflow_dispatch cho deploy từ main, dùng tài khoản SSH giới hạn hoặc runner deploy riêng. Không tự deploy mọi PR lên server giám khảo.
- Chưa thêm workflow deploy tự động vì chưa có server, SSH account, domain và quyền deploy thực tế.

## Checklist bàn giao cho giám khảo
- URL HTTPS có thể truy cập từ Internet; tài khoản riêng, không phải tài khoản admin.
- Dữ liệu demo và model rõ nguồn, không lẫn train/val; chức năng thiếu dữ liệu báo rõ.
- Camera đã qua anonymization và kiểm tra chất lượng, không có đường static bypass.
- Healthcheck/restart hoạt động; thử restart máy demo hoặc VPS, thử rollback; nếu dùng tunnel thì kiểm tra lại URL sau restart.
- Kiểm thử concurrent users theo số giám khảo dự kiến; ghi p95 API/FPS/memory thực đo.
- Có video demo dự phòng và hướng dẫn sử dụng 1 trang.

Tham khảo chính thức:
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow
- https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners
- https://caddyserver.com/docs/automatic-https
- https://caddyserver.com/docs/caddyfile/directives/basic_auth
