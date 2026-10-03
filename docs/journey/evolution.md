# Quan sát và cải tiến theo A-Evolve

Các thay đổi dưới đây được rút từ kiểm tra mã, HTTP tests và hành vi trình duyệt. Không tạo skill tổng quát từ một lỗi đơn lẻ; lưu kiến thức có thể kiểm chứng và regression test tại đúng dự án.

| Quan sát | Nguyên nhân cụ thể | Sửa và gate |
|---|---|---|
| Draft stale không lưu được sau lựa chọn thay thế | Phiên bản server được đọc sau khi draft đã thay hidden field | Chụp snapshot server trước restore; cho đọc nội dung server và chỉ dùng version đã chụp khi người dùng chủ động thay thế. Browser đã xác minh lượt save thành công. |
| Nhu cầu lưu thành công nhưng banner draft còn trở lại | Form có hai hidden `expected_version`, khiến JS nhận RadioNodeList thay input | Xóa field thừa; test HTML khẳng định một field khi chưa có và đã có record. Browser offline → restore → save → reload đã xác minh không còn banner. |
| Pin sát góc thay vì đúng chỗ click | Tọa độ 0–1 bị đưa thẳng vào đơn vị phần trăm | Nhân 100 tại property model; test 0,5/0,25 → 50%/25%, browser click giữa ảnh gần 50%/50%. |
| Chỉ nhập thuê có thể bị coi như đã biết toàn bộ đầu kỳ | Các loại khoản chưa có row bị ngầm cộng 0 | Mỗi loại monthly/deposit/initial chưa nhập tạo unknown; test omitted periods, UI yêu cầu nhập 0 có nguồn nếu đã xác nhận không phát sinh. |
| Tin ghim cũ dẫn tới anchor không có trong 50 tin đầu | Chat chỉ tải trang lịch sử cuối | Link tin nguồn chọn message có ACL theo conversation, tải lân cận rồi cuộn tới source; regression test tin nguồn nằm ngoài cửa sổ ban đầu. |
| Badge còn đếm thông báo workspace không vào được | Count không lọc membership/status | Lọc cùng phạm vi workspace hiện tại; test giữ notification match hợp lệ và bỏ notification workspace đã đóng. |
| Hash ảnh có thể đọc toàn bộ file trước kiểm tra giới hạn | Receipt hash chạy trước ImageUploadForm | Gate số file/action/size trước hash; hash theo chunks. Test file quá giới hạn, file ngoài action và upload retry. |
| Reload sau khi mất phản hồi gửi chat có thể tạo UUID mới | Draft trước đó chỉ giữ nội dung, không giữ UUID lần gửi | Lưu client UUID và nội dung lần thử trong draft; giữ UUID khi thử lại cùng tin, tạo mới khi sửa nội dung. HTTP test dùng cùng UUID với hai mutation key, chỉ tạo một Message; UI kiểm tra khôi phục/gửi/dọn draft. |

Kiến thức duy trì cho lần chạy sau:

1. Test HTTP JSON và database không thay thế việc thử form HTML/JS trên trình duyệt. Kiểm tra shape DOM và dọn local draft sau success là một phần của nghiệm thu autosave.
2. Kiểm chứng tranh chấp SQLite phải dùng file và cùng transaction mode với runtime. Bốn ca concurrent nằm trong suite với `config.test_settings`; ca bị skip trên memory không được ghi nhận là concurrency đã qua.
3. Chỉ đếm consent theo phiên bản room/scenario/membership/agreement hiện tại. Test xác nhận cùng lúc sửa cost là gate riêng, không suy ra từ unique constraint.

Gate: các sửa nhắm lỗi quan sát được, có đường kiểm tra cụ thể, giữ scorer và các trạng thái đồng ý độc lập. Hồ sơ đề xuất gốc không bị đổi trạng thái duyệt sản phẩm.
