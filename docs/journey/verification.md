# Bằng chứng kiểm tra tích hợp

Ngày kiểm tra: 2026-10-03. Nhánh: `codex/roommate-journey`. Dữ liệu UI là các tài khoản và căn mẫu cục bộ.

## Kiểm thử tự động

Suite gồm các kiểm thử pilot hiện có, phân bổ VND, command/HTTP/ACL/version của `journey` và bốn kiểm thử ghi đồng thời trên SQLite file. Command tái lập: `python manage.py test --settings=config.test_settings`. Lượt kiểm tra cuối chạy **67 tests, OK**, không skip bốn ca concurrency. System check, kiểm tra migration và JavaScript syntax đều qua.

Các kịch bản được kiểm tra trực tiếp:

- Lưu khác Like; Like một chiều không mở chat; hai chiều chỉ tạo một pair/conversation. Undo trước match, từ chối undo sau match; mutation retry không lặp side effect.
- Người ngoài không đọc/gửi chat hoặc đọc căn/ảnh riêng; block hai chiều và block từ pilot thu hồi quyền workspace/chat. Match lại không hồi sinh conversation cũ.
- Lời mời chỉ người nhận được trả lời; snapshot chia sẻ tách khỏi bản riêng; notes chỉ người viết đọc; dữ liệu HTML được escape.
- Cursor ký có trang kế tiếp không trùng và từ chối danh sách đã đổi; compare chỉ cho 2–3 người đã lưu. Card không tiết lộ contact.
- Chia VND bảo toàn tổng qua 200 bộ tỷ trọng/số tiền; unknown/estimated/deposit, budgets, các giá trị sai và các loại khoản tiền chưa nhập. Formset căn giữ quyền của các khoản thuộc căn khác.
- Ý kiến độc lập; đề xuất cần chi phí và nguồn; từng consent và phiên bản; sửa cách chia hoặc agreement không dùng lại xác nhận cũ. Điều khoản trống hoặc chưa đồng ý không thể chốt.
- Lịch xem đổi giờ yêu cầu phản hồi lại; hủy lịch; checklist và evidence; task template không tạo lặp, chỉ phân công thành viên, sửa có expected version.
- Thông báo durable, retry/dedupe/preferences/membership; badge bỏ thông báo workspace đã đóng; resume không chuyển ra URL ngoài và kiểm tra quyền.
- Ảnh hợp lệ, byte limit, UUID, ACL, tọa độ, không có URL công khai, upload retry không tạo ảnh trùng. CSRF, POST-only và feature off.
- Race: Like hai chiều; tám request lặp cùng mutation key; block với match; consent với thay đổi cost scenario. Không dùng test SQLite trong bộ nhớ để chứng minh concurrency file.

## Thử trên trình duyệt

Thực hiện trên in-app browser với server Django cục bộ tại `127.0.0.1:8765`:

1. Đăng nhập An, lưu Bình, gửi Like bằng bàn phím; đổi sang Bình, xem incoming Like và Like lại. Chat xuất hiện sau quyết định thứ hai.
2. Sửa gợi ý mở đầu, gửi tin; mời cùng tìm. An xem lời mời và đồng ý; workspace mới mở.
3. Thêm căn với thuê, cọc, khoản một lần và Internet. Rời trang rồi khôi phục draft: khoản Internet động vẫn được phục hồi và lưu đúng. Kết quả 6.200.000 VND/tháng, 12.200.000 VND đầu kỳ; mỗi người 3.100.000/tháng và 6.100.000 đầu kỳ khi chia đều.
4. Làm server có phiên bản căn mới trong lúc còn draft mẫu; reload, khôi phục và đọc phần đối chiếu server. Chỉ sau nút chủ động lưu thay thế mới ghi bản nháp vào phiên bản hiện tại.
5. Lưu scenario, đề xuất căn: cả hai đều còn chưa xác nhận. An và Bình xác nhận bằng hai lần đăng nhập riêng. Soạn agreement, tự lưu, mỗi người đồng ý năm điều khoản và xác nhận toàn bộ. Chỉ sau đó nút bắt đầu chuyển vào hoạt động.
6. Thêm checklist chuyển vào. Kiểm tra workspace ở viewport 390 px: `scrollWidth == clientWidth`, không tràn ngang.
7. Upload ảnh giả lập; chạm ảnh rồi ghim bằng Enter. Vị trí click gần giữa cho style khoảng `left:50%;top:50%`. Gallery có caption, text câu hỏi và phần chi phí từng người; kiểm tra bố cục điện thoại.
8. Ngừng server khi trang nhu cầu đã tải; lưu báo lỗi kết nối và giữ draft. Khởi động lại, reload, khôi phục và lưu; reload lần nữa giữ nội dung server và không còn banner draft. Kịch bản này đã chạy lại sau khi sửa trường phiên bản trùng.
9. Quẹt trái thật bằng drag trên card Chi: Pass và empty state hiện đúng. Undo đưa card về. Quẹt phải thật: chỉ gửi Like, không tự tạo match. Undo trả dữ liệu thử về trạng thái trước đó.
10. Draft chat được khôi phục sau khi rời trang, gửi rồi reload chỉ thấy một tin và không còn banner draft. Test HTTP riêng gửi cùng client UUID với hai mutation key khác nhau chứng minh retry qua một lượt tải trang không tạo tin trùng. Mã client giữ UUID cùng draft và đổi UUID khi nội dung của lần gửi tiếp theo thay đổi.

Ảnh và log của lần chạy nằm trong thư mục `artifacts` của workspace hỗ trợ: discovery desktop, workspace desktop/mobile, gallery desktop/mobile và test results. Chúng dùng để ghi nhận lượt kiểm tra cục bộ, không được coi là dữ liệu người thật hoặc chứng cứ production.

## Giới hạn của bằng chứng

Đã thử desktop và hai kích thước bố cục điện thoại trên trình duyệt. Chưa có thử thiết bị vật lý, audit toàn bộ WCAG hay benchmark tải lớn. CSS có focus visible/reduced motion và giao diện dùng controls có ngữ nghĩa; thử bàn phím đã xác minh các nút deck và ghim. Chat polling và outbox đã kiểm tra ở cấu hình SQLite hiện tại. Chưa deploy hoặc merge vào `main` trong lượt triển khai này.
