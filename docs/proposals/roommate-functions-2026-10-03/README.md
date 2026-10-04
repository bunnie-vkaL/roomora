# Roomora — ghi nhận đề xuất tính năng ghép trọ

Ngày ghi nhận: 2026-10-03 (UTC+7). Trạng thái: **PROPOSED_UNREVIEWED**.

Gói này ghi nhận nguồn và chuẩn bị phương án tích hợp có điều kiện. Tất cả **42 mục của danh sách nguồn** vẫn có `review_rounds = 0`, `disposition = null`, `enabled = false`. Việc phân tích kỹ thuật hoặc đưa tài liệu vào repository không phải duyệt, loại bỏ, cam kết lịch, hay bật tính năng.

## Hồ sơ

- [Nguồn và tình trạng DOCX](source-record.md)
- [Nội dung danh sách và phương hướng code được truy xuất từ chat](source-excerpts.md)
- [Ma trận đủ 42 mục](feature-matrix.md)
- [Registry có cấu trúc](feature-register.json)
- [Phương án, điều kiện, dữ liệu và thứ tự phụ thuộc](integration-options.md)
- [Ghi nhận A-Evolve và bài học có bằng chứng](evolution.md)
- [Kiểm tra kỹ thuật gói tài liệu](review.md)

Mốc repository đã kiểm tra: [`a53c16d4c0398d5de40c702a681d5e276cfaa6a9`](https://github.com/bunnie-vkaL/roomora/commit/a53c16d4c0398d5de40c702a681d5e276cfaa6a9). Không có `AGENTS.md` trong cây repository tại mốc này.

**DOCX gốc chưa được nhận:** chỉ đọc được liên kết và tên `Roommate_Functions_Phuong_Huong_Code.docx` trong chat; không có bytes để lưu hay kiểm tra hash. Các excerpt là bản chép nội dung chat, không phải nội dung được trích từ DOCX. Khi có file gốc, đối chiếu trước khi đổi source verification.

Chat gốc: [Nghiên cứu tính năng ghép trọ](chatgpt-conversation://6abfe260-2c78-83ec-a677-124b9f2c2b80). Nội dung được xem là đầu vào sản phẩm. Stack, ưu tiên MVP và thứ tự code trong nguồn đều chưa trở thành quyết định của Roomora.

`plan.md` hiện đặt chat, listings, chia tiền và push ở phạm vi “Later”. Gói này giữ chúng như đề xuất chờ cân nhắc, không sửa quyết định pilot hiện hữu. Gộp PR tài liệu cũng không thay trạng thái của đề xuất; cần quyết định riêng cho từng ID và phụ thuộc.

## Tình trạng ghi lên GitHub

Ở lần truy cập đầu, kết nối GitHub đọc được repo nhưng trả `403 Resource not accessible by integration` cho cả tạo nhánh và tạo issue. Ngày 2026-10-03, clone bằng Git đã thành công tại cùng commit baseline; gói được chuẩn bị trên nhánh riêng `codex/roommate-functions-conditional-integration` để ghi nhận bằng Git. Việc ghi nhận tài liệu không thay đổi trạng thái duyệt của đề xuất. DOCX nguyên bản vẫn chưa nhận.
