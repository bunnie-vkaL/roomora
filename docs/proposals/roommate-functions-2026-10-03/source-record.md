# Ghi nhận nguồn

| Thuộc tính | Giá trị |
|---|---|
| Tên chat | Nghiên cứu tính năng ghép trọ |
| Conversation ID | 6abfe260-2c78-83ec-a677-124b9f2c2b80 |
| Tệp được nhắc tới | Roommate_Functions_Phuong_Huong_Code.docx |
| Liên kết trong chat | `sandbox:/workspace/scratch/6c10cbedc39b/Roommate_Functions_Phuong_Huong_Code.docx` |
| Tình trạng binary | NOT_RECEIVED — chưa truy xuất được từ sandbox của chat cũ |
| SHA-256 DOCX | null; không được tạo hash thay cho file chưa có |
| Nguồn đã đọc | read_thread, 5 lượt được trả về, hasMore=false; danh sách và hướng code đầy đủ |
| Trạng thái đề xuất | PROPOSED_UNREVIEWED; 0 vòng duyệt hoặc loại bỏ |
| Repository | bunnie-vkaL/roomora; main |
| Commit baseline | a53c16d4c0398d5de40c702a681d5e276cfaa6a9 |
| Root tree | 597aa4a366d01d176f1b5c14ae47f55a88b2f448 |
| Phạm vi ghi nhận | Excerpt liên quan đề xuất; không sao chép toàn bộ chat hoặc dữ liệu cá nhân từ repo |

## Sai lệch số lượng và nguồn chưa nhận

Danh sách đánh số trong chat có **42 mục (1–42)**. Phần phương hướng code có **41 hàng** vì có mục gộp/tách và thêm hàng Chat; lời giới thiệu DOCX nói “41 đề xuất”. Chưa có DOCX nên không khẳng định nó chứa đủ 42 hay đúng 41 mục. Registry sử dụng R01–R42 theo danh sách đánh số, giữ nguyên tên và vị trí nguồn. R09/R35 và R06/R33 có quan hệ nội dung nhưng không bị xóa như trùng lặp.

Chat cũng nhắc bản `Roommate_Product_Functions_UX_Journey.md` v4, FN48–FN63. Bytes của tài liệu đó chưa truy xuất; không suy ra có đủ FN01–FN63 và không tự gán ID FN cho R01–R42.

Chat là phụ thuộc kỹ thuật rõ ràng của R02/R12/R13. Hàng “Chat” trong phương hướng code được ghi riêng thành **S-CHAT** trong integration-options; không đánh số lại danh sách thành 43 đề xuất và không bỏ qua yêu cầu này.

## Quy trình tiếp nhận DOCX khi có bytes

1. Lưu bản gốc nguyên trạng vào thư mục nguồn của gói, ghi tên, kích thước, thời điểm nhận và SHA-256.
2. Trích nội dung, đối chiếu từng mục với source-excerpts và R01–R42; thêm mapping nếu cấu trúc DOCX khác.
3. Ghi discrepancy log; phần chưa đọc vẫn giữ unverified, không tự sửa nghĩa các mục.
4. Cập nhật `source.docx` trong registry; không đổi trạng thái duyệt của tính năng.
5. Nếu file gốc có dữ liệu riêng tư, kiểm tra phạm vi được phép chia sẻ trước khi đưa binary lên repo công khai.

Hiện không có bản DOCX tái tạo hay file giả mang tên bản gốc.
