# Bắt đầu public Roomora với ngân sách 0 đồng

Hiện tại: mã nguồn đã được chỉnh và kiểm tra cục bộ; chưa có tài khoản hosting, URL public hoặc email gửi thật được kiểm chứng. Các thay đổi chưa được commit/push lên GitHub.

## Việc chủ tài khoản cần làm trước

1. Mở [trang đăng ký PythonAnywhere Free](https://www.pythonanywhere.com/registration/register/beginner/).
2. Tự chọn tên tài khoản, nhập email và mật khẩu, đọc và chấp nhận điều khoản. Hoàn thành xác minh nếu dịch vụ yêu cầu. Không gửi mật khẩu cho trợ lý.
3. Sau khi vào được trang quản lý, chỉ cần gửi tên tài khoản để điều chỉnh đường dẫn và hostname triển khai cho đúng. Chưa cần mua domain hoặc chọn gói trả phí.

Form đăng ký yêu cầu đồng ý Terms and Conditions / Privacy and Cookies Policy. Chủ tài khoản tự thực hiện bước này để tài khoản và cam kết dịch vụ thuộc quyền kiểm soát của mình.

Theo [tài liệu chính thức về tài khoản miễn phí](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/), gói này hiện có một web app với một worker, 512 MiB dung lượng và thời hạn web app một tháng. Cần gia hạn web app khi dịch vụ yêu cầu. Tài khoản mới không có MySQL hoặc tác vụ chạy định kỳ miễn phí. Phương án Roomora dùng SQLite và xử lý thông báo khi người dùng trở lại ứng dụng.

## Phần triển khai kế tiếp

Sau khi có tài khoản, dùng [hướng dẫn triển khai hiện có](free-beta.md) và `deploy/free-beta.env.example` để cấu hình Django. Cần chuyển bản mã nguồn cục bộ hiện tại lên host theo một gói được kiểm tra; checkout `dev` từ GitHub hiện chưa chứa các chỉnh sửa cục bộ. Chỉ chuyển mã cần chạy; không chuyển DB cục bộ, hồ sơ thử, backup, `.env`, session hoặc thư mục ảnh riêng.

Tạo secret mới và thư mục riêng trên host; dùng cấu hình `config.free_beta_settings`. Chỉ ánh xạ static và avatar công khai. DB và ảnh căn/bằng chứng đi qua đường truy cập có kiểm tra quyền. Cài dependencies, migrate, collectstatic và cấu hình WSGI rồi kiểm tra HTTPS, đăng nhập, survey, gợi ý, kết nối hai chiều, chat và quyền xem ảnh.

Email là hạng mục riêng: cấu hình hiện tại yêu cầu khóa Brevo và địa chỉ gửi được phép. Có thể chuẩn bị tài khoản dịch vụ email miễn phí khi đến bước đó; khóa phải lưu ở cấu hình riêng trên host. Chưa có bằng chứng email thật đã gửi hoặc vào inbox. Không đánh dấu sẵn sàng public trước khi thử luồng đặt lại mật khẩu và kiểm tra lỗi gửi.

Mở beta nhỏ sau khi các bước trên đạt; đo tải thực tế trước khi tăng số người dùng. Không có yêu cầu mua gói, domain hay nhập thẻ trong phương án này.
