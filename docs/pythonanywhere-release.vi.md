# Chuyển bản cục bộ lên PythonAnywhere Free

Đây là hướng dẫn cho mã nguồn cục bộ đã chỉnh, chưa phải xác nhận triển khai public thành công. Chủ tài khoản tự tạo Free và chấp nhận điều khoản theo [bước bắt đầu](free-account-start.vi.md). Chưa mua domain hoặc dịch vụ trả phí.

## Gói mã

Ở máy phát triển, dùng Python trong môi trường dự án:

```powershell
.venv\Scripts\python.exe tools/build_free_beta_bundle.py --output ../artifacts/releases/roomora-free-beta-20261004-r2.zip
```

Script chỉ đọc các nhóm mã runtime và tài liệu đã chỉ định. Gói có thư mục `roomora/` và manifest SHA-256 từng tệp, gồm các thay đổi chưa commit. Không kèm `.git`, `.env`, DB, sessions, uploads, backups, dữ liệu nhập, fixtures, virtualenv, kiểm thử hoặc lệnh tạo demo/nhập hồ sơ mẫu. Hash giúp phát hiện tệp thay đổi so với manifest; không phải chữ ký hoặc audit mọi bí mật có thể viết nhầm vào mã nguồn. Đích đã tồn tại bị từ chối, không ghi đè.

Tải gói đã kiểm tra vào tài khoản của chủ sở hữu rồi giải nén trong thư mục home để có `/home/ACCOUNT/roomora`. Khi thực hiện upload, cần xác nhận tài khoản đích và nội dung gói. Không upload thư mục làm việc nguyên trạng. Một checkout `dev` từ GitHub hiện chưa chứa các chỉnh sửa cục bộ này.

## Môi trường và cấu hình riêng

Theo [hướng dẫn chính thức của PythonAnywhere](https://help.pythonanywhere.com/pages/DeployExistingDjangoProject/), tạo virtualenv và web app với **Manual Configuration**, cùng phiên bản Python. Cài `requirements.txt` trong virtualenv. Không dùng runserver làm web app public hoặc cài requirements PostgreSQL/Gunicorn cho gói Free này.

Tạo tệp `/home/ACCOUNT/roomora-env.json` bên ngoài mã nguồn và các thư mục dữ liệu. Dùng tên biến trong `deploy/free-beta.env.example` làm khóa JSON, tất cả giá trị là chuỗi; bỏ dòng `DJANGO_SETTINGS_MODULE` vì loader luôn chọn `config.free_beta_settings`. Giữ tệp chỉ chủ sở hữu đọc được bằng `chmod 600`; không đưa nội dung vào ảnh chụp, lệnh shell hay Git. Sinh SECRET_KEY mới trên host và lưu trực tiếp trong tệp. BREVO_API_KEY và sender cần được chủ tài khoản cấu hình riêng; khóa giả dùng trong rehearsal không gửi được email thật.

Tạo bốn thư mục sibling của mã: `/home/ACCOUNT/roomora_static`, `roomora_media`, `roomora_private`, `roomora_data`. Cấu hình đúng đường dẫn tuyệt đối, hostname và HTTPS origin của tài khoản. Không tự bật tin cậy forwarded-proto/client-IP trước khi kiểm chứng proxy của host ghi đè header. Kiểm tra HTTPS trên host để phát hiện vòng lặp redirect trước khi mời người dùng.

## Cùng cấu hình cho console và WSGI

Trong console đã kích hoạt virtualenv và đang ở `/home/ACCOUNT/roomora`:

```sh
python deploy/free_beta.py --env /home/ACCOUNT/roomora-env.json check --deploy
python deploy/free_beta.py --env /home/ACCOUNT/roomora-env.json migrate --noinput
python deploy/free_beta.py --env /home/ACCOUNT/roomora-env.json collectstatic --noinput
```

Hai cảnh báo HSTS include-subdomains/preload được giữ cố ý; không dùng các cảnh báo đó để bỏ qua lỗi cấu hình khác. Loader kiểm tra vị trí tệp, tên/kiểu biến và quyền POSIX rồi nạp profile Free. Không đọc `.env` development. Sửa **tệp WSGI được liên kết trong Web tab** theo `deploy/pythonanywhere_wsgi.py.example`, thay ACCOUNT và đường dẫn; chỉ sửa `config/wsgi.py` trong mã không cấu hình được WSGI của provider.

Theo [hướng dẫn static chính thức](https://help.pythonanywhere.com/pages/DjangoStaticFiles/), ánh xạ `/static/` tới `roomora_static`; avatar công khai dùng `/media/` tới `roomora_media`. Không ánh xạ mã nguồn, env JSON, SQLite data hoặc `roomora_private`. Sau khi Reload, kiểm tra static thật; route ảnh căn riêng phải qua Django và kiểm tra quyền.

## Trước khi mở beta

Kiểm chứng trên hostname thật: readiness, đăng ký/đăng nhập, survey và lưu tiếp, gợi ý danh sách/quẹt, consent hai chiều, chat gửi/nhận/thu hồi, căn riêng/chung, ảnh riêng, thông báo và đặt lại mật khẩu gửi email thật. Đo tải trên host, kiểm tra dung lượng sau cài đặt, backup/restore và lịch gia hạn web app. Rehearsal cục bộ không thay các kiểm tra này. Hướng vận hành và giới hạn nằm trong [free-beta.md](free-beta.md).
