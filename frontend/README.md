# Frontend BEV Lab

Frontend dùng Next.js, React và Three.js để hiển thị detection thật từ API lab.

## Yêu cầu

- Node.js 22 và npm. File `.nvmrc` giúp người dùng `nvm` chọn đúng phiên bản.
- Python 3.12 để chạy backend FastAPI.
- Thư mục dữ liệu `data/lab` có sẵn trong repo, hoặc khai báo `LAB_DATA_ROOT` ở file `.env` tại thư mục gốc.

Viewer BEV không cần GPU, CUDA, model weight hay API key của OpenAI.

## 1. Chạy backend

Từ thư mục gốc của repository:

```bash
python3.12 -m venv .venv-lab
source .venv-lab/bin/activate
pip install -r requirements-web.txt
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Trên Windows PowerShell, thay hai lệnh đầu bằng:

```powershell
py -3.12 -m venv .venv-lab
.\.venv-lab\Scripts\Activate.ps1
```

Kiểm tra backend tại [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) hoặc Swagger tại [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Nếu dữ liệu nằm ngoài repo, sao chép `.env.example` ở thư mục gốc thành `.env`, rồi đặt đường dẫn tuyệt đối:

```dotenv
LAB_DATA_ROOT=/duong/dan/toi/data/lab
```

## 2. Chạy frontend

Mở terminal khác:

```bash
cd frontend
nvm use                 # bỏ qua nếu máy không dùng nvm nhưng đã có Node 22
cp .env.example .env.local
npm ci
npm run dev
```

Trên Windows PowerShell, lệnh sao chép file môi trường là:

```powershell
Copy-Item .env.example .env.local
```

Mở [http://localhost:3000](http://localhost:3000).

Trình duyệt chỉ gọi đường dẫn tương đối `/api/v1/...`. Next.js chuyển tiếp request tới `API_INTERNAL_URL`, mặc định là `http://127.0.0.1:8000`. Nếu backend chạy ở host hoặc cổng khác, sửa giá trị trong `.env.local` rồi khởi động lại `npm run dev`.

## Kiểm tra trước khi tạo Pull Request

```bash
npm ci
npm run lint
npm run build
```

`npm ci` dùng đúng phiên bản trong `package-lock.json`, giúp các thành viên cài cùng một bộ dependency.

## Xử lý lỗi thường gặp

- `Failed to fetch` hoặc viewer báo lỗi API: kiểm tra backend đang chạy ở cổng 8000 và `API_INTERNAL_URL` đúng.
- API trả `503`: kiểm tra thư mục `data/lab`, hoặc chạy `scripts/check_lab_data.py` theo hướng dẫn tại `docs/LAB_SETUP.vi.md`.
- Trang không render canvas: dùng trình duyệt có WebGL2 và kiểm tra hardware acceleration.
- Đổi `.env.local` nhưng không có tác dụng: dừng và chạy lại `npm run dev`.

Không commit `.env.local` hoặc `.env`; Git đã bỏ qua các file này. Chỉ `.env.example` được commit để làm mẫu chung.
