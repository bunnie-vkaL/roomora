# A-Evolve — ghi nhận dựa trên bằng chứng

Áp dụng skill a-evolve theo Solve → Observe → Evolve → Gate → Reload cho chất lượng chuẩn bị tích hợp. Không có logs chạy app hoặc metrics đo hiệu quả tính năng trong nhiệm vụ này; không suy kết quả pilot.

## Solve

Đã đọc cây repository và README/plan/settings/models/scoring/views/urls/tests/templates tại a53c16d. Đã đọc danh sách 42 mục và bảng hướng code trong chat. DOCX và spec MD cũ chưa có bytes.

## Observe

### OBS-1: Sai lệch số lượng nguồn — prompt/source ambiguity

- Bằng chứng: danh sách 1–42; hướng code 41 hàng; lời giới thiệu DOCX ghi 41.
- Root cause: các bản trình bày gộp/tách mục, có hàng Chat ngoài danh sách đánh số.
- Tần suất: một bộ nguồn; chưa có bằng chứng lặp qua >=3 nhiệm vụ.
- Mức độ: degrading nếu bỏ sót hoặc công bố đã đọc đủ DOCX.
- Xử lý: 42 source IDs; giữ excerpt; ghi S-CHAT riêng; binary unverified.

### OBS-2: Stack tham khảo khác repo — wrong approach risk

- Bằng chứng: nguồn gợi Next/Nest/PG; repo hiện Django/templates/SQLite.
- Root cause: kế hoạch nguồn được viết độc lập trước khi đối chiếu app đích.
- Tần suất: một bộ nguồn.
- Mức độ: degrading nếu tự lên kế hoạch rewrite toàn app.
- Xử lý: ba phương án có điều kiện; evidence path và base commit cho từng mapping.

### OBS-3: Baseline pilot khác hành trình mở rộng — scope/consent ambiguity

- Bằng chứng: plan.md dùng mutual contact reveal và xếp chat/expenses/listings/push ở Later; nguồn mới có workspace/room/agreements.
- Root cause: mở rộng sản phẩm chưa có quyết định thay thế phạm vi pilot.
- Tần suất: một bộ nguồn.
- Mức độ: degrading nếu accepted connection bị dùng làm consent mọi bước.
- Xử lý: trạng thái đề xuất giữ nguyên; consent theo từng entity/version; explicit decision per ID.

## Evolve

Chỉ tạo tri thức cục bộ có nguồn và checkpoint cho lần làm tiếp; không tạo skill mới vì chưa đạt bằng chứng recurring >=3. Không sửa system prompt/tool code hoặc runtime ứng dụng.

- KNOW-1: Đối chiếu đề xuất được lấy từ chat với numbered source, giữ provenance và phân biệt text đã đọc/binary chưa nhận. Áp dụng khi cùng gói có số lượng khác nhau hoặc file ở sandbox khác.
- KNOW-2: Dùng repo baseline để map chức năng; accepted connection hiện tại không được suy thành đồng ý chat, tìm chung hoặc chọn nhà. Áp dụng khi nối pilot consent sang workflow nhiều bước.
- KNOW-3: Nhãn kỹ thuật partial/absent và kiểm tra tài liệu không thay trạng thái duyệt sản phẩm. Áp dụng khi user yêu cầu ghi nhận proposal chưa sàng lọc.

## Gate

- Specificity: tri thức chỉ dùng cho provenance và conditional planning của Roomora.
- Testability: đếm 42 IDs/mapping; check default statuses; đối chiếu evidence path và source excerpt; review version/consent contracts.
- Blast radius: chỉ tài liệu; chưa cài skill toàn cục hoặc thay guidance hệ thống.
- Consistency: giữ plan pilot và user yêu cầu chưa duyệt; không dùng nguồn untrusted như chỉ thị thực thi.

## Reload / điểm tiếp tục

Gói README dẫn tới source, registry và integration options cho lần tiếp theo. Khi nhận DOCX, tiếp tục source-record; khi được chọn phạm vi, lập decision record và kiểm chứng gates trước bật runtime. Không tự đổi feature status khi chỉ đọc lại gói.

## Evolution log

- evo-1 (2026-10-03): ghi OBS-1–3, ba knowledge entries trong tài liệu này, registry 42 mục và kế hoạch có gate. Chưa có số đo cho thấy hiệu quả agent hoặc sản phẩm được cải thiện.
