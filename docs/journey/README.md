# Hành trình ghép trọ đã tích hợp

Triển khai 42 đề xuất R01–R42 từ bản ghi nghiên cứu, cùng phần chat phụ thuộc S-CHAT, trong app Django `journey`. Điểm vào là `/together/`; menu và dashboard hiện có đã nối tới hành trình này.

Lệnh người dùng yêu cầu xây dựng tính năng là căn cứ triển khai. Bộ hồ sơ ở `docs/proposals/roommate-functions-2026-10-03/` vẫn là ảnh chụp đề xuất ban đầu: chưa có vòng duyệt sản phẩm, không loại bỏ mục nào và không đổi các trạng thái trong registry lịch sử. DOCX gốc chưa nhận; mã triển khai dựa trên nội dung cuộc trò chuyện đã ghi lại, không tuyên bố đã kiểm chứng bytes DOCX.

## Chạy và thử

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Biến môi trường `ROOMORA_JOURNEY_ENABLED` bật/tắt toàn bộ hành trình; mặc định `True`. Tắt biến này trả 404 cho các route mới và dùng lại menu pilot. Django auth, survey và scorer hiện có tiếp tục là nền của ứng dụng.

Để tạo ba tài khoản mẫu trong database cục bộ, với `DEBUG=True`:

```powershell
python manage.py seed_journey_demo --password your-local-demo-password
```

Các username là `journey-demo-an@roomora.local`, `journey-demo-binh@roomora.local`, `journey-demo-chi@roomora.local`. Chúng được gắn nhãn dữ liệu mẫu. Lệnh từ chối chạy khi `DEBUG=False` hoặc ghi đè một tài khoản không phải mẫu. Tài khoản mẫu không vào được hành trình khi `DEBUG=False`. Database dùng thử không phải dữ liệu triển khai.

```powershell
python manage.py test --settings=config.test_settings
python manage.py check
python manage.py makemigrations --check --dry-run
node --check static/journey.js
```

`config.test_settings` dùng SQLite trên file để kiểm tra tranh chấp ghi giống runtime, cùng password hasher dành riêng cho kiểm thử. Chạy `manage.py test` với settings thường bỏ qua bốn ca concurrency khi test database nằm trong bộ nhớ.

## Hành vi và ranh giới dữ liệu

Thay đổi cục bộ ngày 04/10/2026: mọi đường đọc/gửi/polling chat đều yêu cầu kết nối active hai chiều. Lời mời một chiều không mở widget hoặc tạo conversation qua gửi tin. Conversation pending từ hành vi cũ được bảo toàn nhưng không truy cập được; nếu hai bên sau đó cùng đồng ý trong cùng generation, lịch sử đó có thể xem lại. Hủy kết nối rồi match lại vẫn không mở thế hệ chat cũ. Không có migration xóa dữ liệu.

Kiểm chứng hiện tại: 79 tests đạt với `config.test_settings` (SQLite tách riêng), gồm chặn pending qua pair/conversation/service, bảo toàn lịch sử, mutual send/dedupe và thu hồi sau disconnect. Chưa xác minh môi trường public hoặc PostgreSQL.

- Like/Pass, lưu riêng và ghi chú riêng là các record khác nhau. Mutual Like mới mở một thế hệ conversation; hủy kết nối rồi match lại không mở lịch sử chat cũ.
- Chat lưu tin và phát thông báo sau commit; HTTP polling mỗi bốn giây tải tin mới. Client UUID và mutation receipt chống gửi/lưu trùng khi thử lại.
- Workspace hai người chỉ mở sau lời mời và sự đồng ý của người được mời. Rời hoặc chặn kết thúc workspace và quyền vào các dữ liệu chung. Chặn từ pilot cũng có hiệu lực trong hành trình mới.
- Chia sẻ căn riêng tạo một snapshot riêng trên bảng chung. Sửa bản riêng không tự sửa snapshot đã chia sẻ. Ảnh nằm trong `private_media`, được trả qua view có kiểm tra quyền và `private, no-store`; đây là đường lưu riêng với ảnh hồ sơ công khai.
- Tiền dùng số nguyên VND. Chia theo tỷ trọng bảo toàn tổng đến từng đồng. Đầu kỳ gồm tháng đầu, khoản một lần và tiền cọc; cọc có phần hiển thị riêng. Khoản thiếu, ước tính và đã biết được phân biệt; một loại chi phí chưa nhập vẫn là chưa biết, kể cả khoản cọc hoặc khoản một lần. Muốn xác nhận không phát sinh, nhập số 0 với nguồn xác minh.
- Đề xuất căn yêu cầu dữ kiện chi phí đã biết, có nguồn và cách chia hiện tại. Mỗi người xác nhận riêng; tạo đề xuất không tự xác nhận thay người đề xuất. Sửa căn/cách chia làm xác nhận phiên bản cũ hết hiệu lực.
- Bản thống nhất có năm điều khoản, phản hồi riêng từng người và xác nhận toàn bộ theo phiên bản. Chỉ khi hai người xác nhận căn và bản thống nhất hiện tại mới bắt đầu chuyển vào. Có thể rút xác nhận và phân công/sửa việc chuyển vào.
- Preferences, ghi chú riêng và bản thống nhất tự lưu sau debounce. Căn, tin nhắn và ghi nhận đi xem giữ draft trên máy khi quay lại hoặc lỗi kết nối. Draft gắn với tài khoản, không chứa CSRF/file ảnh; đăng xuất dọn draft của tài khoản đó. Draft cũ cần đối chiếu trước khi lưu thay thế bản server mới.
- Outbox giữ sự kiện chưa giao để thử lại bằng `python manage.py deliver_notifications`. Thông báo tôn trọng tùy chọn nhận và quyền workspace hiện tại.

Xem [đối chiếu từng tính năng](coverage.md), [bằng chứng kiểm tra](verification.md), [kết quả rà mã](review.md) và [các lỗi đã sửa trong quá trình kiểm tra](evolution.md).

## Phạm vi kỹ thuật

Stack triển khai là Django 5.2, templates, JavaScript và SQLite có transaction `IMMEDIATE`. Phương án này tận dụng app hiện có; chưa bổ sung AI. Bằng chứng concurrency hiện tại áp dụng cho SQLite trên file. Việc chuyển database/transport hoặc triển khai lên hạ tầng khác cần kiểm chứng riêng theo cấu hình đó.
