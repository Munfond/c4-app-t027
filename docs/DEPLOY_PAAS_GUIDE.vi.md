# Hướng dẫn Triển khai Web theo Phương án B (Cloud PaaS: Vercel + Render + Supabase)

Phương án này sử dụng 100% dịch vụ đám mây miễn phí (Free Tier), không cần mua máy chủ VPS, tự động có chứng chỉ bảo mật HTTPS và dễ dàng gắn tên miền riêng.

---

## Tổng quan kiến trúc

- **Frontend**: Next.js 16 (React 19 + Three.js) deploy lên **Vercel** (Global CDN, tự động cấp HTTPS).
- **Backend**: FastAPI (Python 3.12) deploy lên **Render** (Containerized Docker Web Service).
- **Database**: PostgreSQL 16 trên **Supabase** (hoặc Neon) lưu trữ toàn bộ dữ liệu thực nghiệm (Frames, Detections, Benchmarks) để code mở trên GitHub không làm lộ dữ liệu.

---

## Bước 1: Tạo Database PostgreSQL trên Supabase (2 phút)

1. Truy cập [supabase.com](https://supabase.com) và đăng nhập bằng tài khoản GitHub.
2. Bấm **New Project**, đặt tên (vd: `p027-db`), nhập mật khẩu database an toàn và chọn Region: **Southeast Asia (Singapore)** để tối ưu tốc độ kết nối về Việt Nam.
3. Sau khi tạo xong, vào mục **Project Settings** → **Database** → kéo xuống mục **Connection string** → chọn tab **URI** (hoặc Connection pooling).
   - Định dạng chuỗi kết nối sẽ có dạng:
     ```text
     postgresql://postgres.[project-ref]:[password]@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require
     ```
4. **Nạp dữ liệu từ máy local lên Supabase:**
   Mở terminal tại thư mục dự án và chạy lệnh sau (thay chuỗi kết nối thật của bạn):
   - **Trên Windows PowerShell:**
     ```powershell
     $env:DATABASE_URL="postgresql://postgres.xxx:matkhau@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require"
     .\.venv-lab\Scripts\python.exe scripts/seed_database.py
     ```
   - **Trên Linux/macOS:**
     ```bash
     DATABASE_URL="postgresql://postgres.xxx:matkhau@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres?sslmode=require" python3 scripts/seed_database.py
     ```
   *Kết quả:* Toàn bộ 81 frames, ~140.000 detections và bảng benchmark sẽ được tạo bảng và nạp trực tiếp vào Supabase.

---

## Bước 2: Deploy Backend lên Render (3 phút)

1. Truy cập [render.com](https://render.com) và đăng nhập bằng GitHub.
2. Bấm nút **New +** ở góc trên bên phải → chọn **Web Service**.
3. Chọn repository `P-027` từ danh sách GitHub repositories của bạn.
4. Cấu hình thông tin dịch vụ:
   - **Name**: `p027-backend` (hoặc tên tùy thích).
   - **Region**: `Singapore`.
   - **Runtime**: `Docker`.
   - **Instance Type**: `Free`.
5. Kéo xuống mục **Environment Variables** (Biến môi trường) và thêm:
   - `DATABASE_URL`: dán chuỗi kết nối PostgreSQL từ Supabase ở Bước 1.
   - `APP_ENV`: `production`
   - `PORT`: `8000`
   - `ANONYMIZER_ENABLED`: `false`
   - `CORS_ORIGINS`: `https://*.vercel.app,http://localhost:3000`
6. Bấm **Create Web Service**.
7. Chờ Render build Docker image khoảng 2–3 phút. Khi hoàn tất, Render sẽ cấp cho bạn một URL có dạng:
   `https://p027-backend.onrender.com`
8. **Kiểm tra hoạt động:**
   Mở trình duyệt truy cập:
   - `https://p027-backend.onrender.com/health` → Trả về `{"status": "ok", "env": "production"}`
   - `https://p027-backend.onrender.com/api/v1/lab/scenes` → Trả về danh sách Scene từ database Supabase.

---

## Bước 3: Deploy Frontend lên Vercel (2 phút)

1. Truy cập [vercel.com](https://vercel.com) và đăng nhập bằng GitHub.
2. Bấm **Add New...** → **Project**.
3. Chọn repository `P-027` và bấm **Import**.
4. **Cấu hình quan trọng tại trang Configure Project:**
   - Mục **Root Directory**: Bấm nút **Edit** và chọn thư mục `frontend` (bấm Continue).
   - Mục **Framework Preset**: Vercel sẽ tự động nhận diện là **Next.js**.
   - Mục **Environment Variables**:
     - Key: `API_INTERNAL_URL`
     - Value: URL Backend Render đã lấy ở Bước 2 (vd: `https://p027-backend.onrender.com`, không để dấu `/` ở cuối).
5. Bấm nút **Deploy**.
6. Vercel sẽ build giao diện trong khoảng 1 phút và cấp cho bạn một tên miền HTTPS chính thức:
   `https://p-027.vercel.app` (hoặc `https://p027-xxx.vercel.app`).

---

## Bước 4: Gắn Custom Domain riêng (Tùy chọn)

Nếu bạn có mua tên miền riêng (ví dụ `adas-lab.com` hoặc `vinfast.yourdomain.com`):

### 1. Gắn domain cho Frontend (Giao diện chính):
- Trong dashboard Vercel của dự án, vào **Settings** → **Domains**.
- Nhập domain của bạn (vd: `lab.yourdomain.com`) và bấm **Add**.
- Vercel sẽ hiển thị bản ghi DNS cần cấu hình (thường là một bản ghi CNAME trỏ về `cname.vercel-dns.com`).
- Vào trang quản lý tên miền của bạn và thêm bản ghi CNAME đó. Vercel sẽ tự động xác thực và cấp chứng chỉ SSL trong vòng 1-2 phút.

### 2. Gắn domain cho Backend API (Nếu cần):
- Trong dashboard Render của `p027-backend`, vào **Settings** → **Custom Domains**.
- Nhập subdomain (vd: `api-lab.yourdomain.com`).
- Thêm bản ghi CNAME trên nhà cung cấp DNS trỏ về địa chỉ Render cung cấp.
- Cập nhật lại biến `API_INTERNAL_URL` trên Vercel thành `https://api-lab.yourdomain.com`.

---

## Kiểm thử sau khi triển khai

1. Truy cập trực tiếp link Vercel: `https://your-app.vercel.app/lab`
2. Đổi giữa các Scene và chọn Model (ví dụ `our_cl`, `official_lidar`):
   - Bản đồ 3D LiDAR và các hộp nhận diện 3D hiển thị đầy đủ.
   - Thử tính năng Timeline Playback (phát keyframe tuần tự).
3. Truy cập `https://your-app.vercel.app/benchmarks`:
   - Bảng so sánh chỉ số mAP, NDS, latency load trực tiếp từ Supabase PostgreSQL.
