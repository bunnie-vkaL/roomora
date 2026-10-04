# Nội dung đề xuất được truy xuất từ chat

Nguồn: cuộc trò chuyện [Nghiên cứu tính năng ghép trọ](chatgpt-conversation://6abfe260-2c78-83ec-a677-124b9f2c2b80), đọc ngày 2026-10-03. Đây là nội dung trả lời trợ lý ở hai lượt “Chỉ cần list…” và “Gửi lại có phương hướng code”. Các đề xuất, stack và ưu tiên bên dưới **chưa được duyệt**. Không phải bản trích DOCX.

## Danh sách gốc

Các tính năng và trải nghiệm đề xuất cho ứng dụng:

**Tìm bạn ở cùng**

1. Quẹt phải để muốn kết nối, quẹt trái để bỏ qua.
2. Hai bên cùng quan tâm thì match và mở chat.
3. Hoàn tác lượt quẹt nhầm.
4. Lưu người để xem sau, độc lập với Like.
5. Xem danh sách người đã muốn kết nối với mình.
6. Thẻ hồ sơ hiển thị ngân sách, thời điểm chuyển vào, nhu cầu và thói quen.
7. Giải thích điểm phù hợp và điều cần trao đổi.
8. So sánh 2–3 người đã lưu.
9. Xem trước nhịp sinh hoạt chung.
10. Ghi chú riêng về từng người.
11. Chặn, báo cáo và hủy kết nối.

**Trao đổi và cùng tìm nhà**

12. Gợi ý lời mở đầu có thể chỉnh sửa.
13. Ghim thông tin quan trọng và tóm tắt việc còn chưa thống nhất.
14. Đề xuất cùng tìm nhà; đối phương đồng ý để mở không gian chung.
15. Lưu căn riêng trước khi có người cùng tìm.
16. Tìm người cùng cân nhắc một căn đã lưu.
17. Thêm link, ảnh và thông tin căn vào bảng tìm nhà chung.
18. Mỗi người đánh dấu: quan tâm, chưa chắc hoặc không phù hợp.
19. So sánh các căn theo nhu cầu của cả hai.
20. Tính tiền hàng tháng và tiền đầu kỳ cho từng người.
21. Thử các cách chia chi phí, cảnh báo vượt ngân sách.
22. Hiển thị rõ khoản chưa biết và thông tin cần kiểm tra.
23. Phối hợp lịch đi xem nhà.
24. Checklist đi xem theo từng căn.
25. Ghi chú, ảnh và bằng chứng sau khi đi xem.
26. Đề xuất chọn căn và xác nhận riêng của từng người.

**Thống nhất và chuyển vào**

27. Tạo bản nháp thống nhất về tiền, vệ sinh, khách, giờ yên tĩnh và riêng tư.
28. Theo dõi điều khoản đã đồng ý và còn cần trao đổi.
29. Yêu cầu xác nhận lại khi thay đổi nội dung quan trọng.
30. Lập kế hoạch chuyển vào và phân công việc.
31. Khôi phục đúng việc đang làm khi mở lại ứng dụng.
32. Thông báo thay đổi có ảnh hưởng đến quyết định.

**Trải nghiệm thị giác và thao tác**

33. Thẻ quẹt cân bằng ảnh cá nhân với thông tin quyết định ở ghép.
34. Có nút tương đương thao tác quẹt, dùng được bằng bàn phím.
35. Hình “một ngày ở cùng” để so sánh nhịp sinh hoạt.
36. Gallery “căn này với chúng mình”, kèm chi phí từng người.
37. Ghim câu hỏi trực tiếp lên ảnh căn.
38. Avatar và ý kiến từng người xuất hiện cạnh mỗi phương án.
39. Trạng thái rõ: match → cùng tìm → chọn căn → chuyển vào.
40. Giao diện gần gũi, màu ấm, chữ dễ đọc, chuyển động nhẹ.
41. Tự lưu, giữ dữ liệu khi quay lại hoặc lỗi mạng.
42. Màn hình trống/lỗi có hành động tiếp theo rõ ràng.

**Ưu tiên MVP:** quẹt và match, chat, lưu người/căn, không gian tìm nhà chung, ý kiến từng người, tính chi phí, xác nhận chọn căn và bản thống nhất.

## Phương hướng code gốc

Được để tôi giúp bạn làm điều đó. Dưới đây là danh sách đề xuất **kèm phương hướng code**, để chuyển thành backlog triển khai. Đăng nhập và thiết lập vị trí nằm ngoài phạm vi.

Stack tham khảo: **Next.js + TypeScript** cho giao diện, **NestJS** cho backend, **PostgreSQL** lưu dữ liệu, **WebSocket** cho chat và cập nhật chung. Chưa cần AI ở bản đầu.

### 1. Tìm bạn ở cùng

| Tính năng | Phương hướng code |
|---|---|
| Quẹt người | Component `SwipeDeck` xử lý Pointer Events; có nút Like/Pass tương đương. Backend trả danh sách bằng cursor pagination. |
| Match hai chiều | Lưu `SwipeDecision`; khi cả hai Like, tạo `Connection` và `Conversation` trong một transaction. Unique constraint chống tạo trùng. |
| Hoàn tác quẹt | Lưu lịch sử quyết định; cho rút lượt cuối chưa tạo match. Đã match thì dùng thao tác hủy kết nối riêng. |
| Lưu xem sau | Bảng `SavedCandidate`, độc lập với Like/Pass. |
| Người đã quan tâm mình | Query các Like đến còn hiệu lực; loại người bị chặn hoặc đã ngừng tìm. |
| Thẻ hồ sơ | Backend trả `CandidateCardView`: ngân sách, ngày chuyển, nhu cầu, điểm hợp và điều cần hỏi. |
| Giải thích độ phù hợp | Rule engine lọc điều kiện bắt buộc trước, đánh giá sở thích sau; trả lý do từ dữ liệu gốc. |
| So sánh người | API nhận tối đa ba người; trả dữ liệu cùng cấu trúc để giao diện đối chiếu theo tiêu chí. |
| Nhịp sống chung | Lưu các khoảng giờ sinh hoạt; component timeline đặt hai lịch cạnh nhau, ghi rõ phần chưa biết. |
| Ghi chú riêng | Bảng `PrivateNote`; chỉ tác giả được đọc, không đưa vào hồ sơ công khai. |
| Chặn/báo cáo/hủy kết nối | Các command riêng; backend kiểm tra block tại cả discovery, match và gửi tin. |

### 2. Trao đổi và cùng tìm nhà

| Tính năng | Phương hướng code |
|---|---|
| Chat | Lưu tin vào PostgreSQL rồi phát sự kiện WebSocket sau khi thành công; phân trang lịch sử, chống gửi trùng. |
| Gợi ý mở lời | Template từ điểm chung và điều chưa rõ; đổ vào ô soạn, người dùng sửa rồi gửi. |
| Ghim/tóm tắt trao đổi | Bản đầu dùng `PinnedFact` và trạng thái đề xuất/đã xác nhận; mỗi mục liên kết về tin nguồn. |
| Đồng ý cùng tìm | Bảng `SearchWorkspace` và `WorkspaceMember`; trạng thái mời/chấp nhận/rời. Match chưa tự tạo sự đồng ý cùng tìm. |
| Lưu căn riêng | `RoomOption` thuộc người dùng; thêm link và dữ kiện tối thiểu, cho phép thiếu giá/ảnh. |
| Tìm bạn theo căn đã lưu | Truyền `roomContextId` vào đề xuất người; dùng căn làm ngữ cảnh giải thích, vẫn giữ điều kiện bắt buộc cá nhân. |
| Bảng nhà chung | Bảng liên kết `WorkspaceRoom`; người dùng chủ động thêm căn riêng vào workspace. |
| Ý kiến từng người | `RoomOpinion` unique theo căn + thành viên; lưu quan tâm/chưa chắc/không phù hợp. |
| So sánh căn | Backend chuẩn hóa giá và chi phí từng người; frontend hiển thị 2–3 căn theo cùng tiêu chí. |
| Tính và thử chia tiền | Hàm thuần `calculateSharedCosts()`; lưu tiền bằng số nguyên VND, tính phần tháng/đầu kỳ và khoản vượt trần. |
| Khoản chưa rõ | Field có trạng thái `KNOWN / ESTIMATED / UNKNOWN`; không chuyển thiếu dữ liệu thành 0. |
| Hẹn đi xem | `ViewingPlan` có thời gian đề xuất và phản hồi từng người; chỉ confirmed khi đủ đồng ý. |
| Checklist đi xem | Sinh checklist từ dữ kiện căn còn thiếu; lưu mục đã kiểm tra và ghi chú. |
| Bằng chứng sau xem | `ViewingEvidence` lưu ảnh, ghi chú, người tạo, thời điểm; dùng object storage cho ảnh. |
| Đề xuất/chọn căn | `RoomChoiceProposal` có version; từng người xác nhận cùng version. Đổi căn hoặc phân bổ tiền làm xác nhận cũ hết hiệu lực. |

### 3. Thống nhất và chuyển vào

| Tính năng | Phương hướng code |
|---|---|
| Bản thống nhất | `Agreement` gồm các điều khoản có cấu trúc; điền nháp từ dữ kiện đã chia sẻ, cho sửa. |
| Xác nhận từng người | `AgreementConsent` gắn với member + agreement version. |
| Xác nhận lại khi sửa | Tăng version khi đổi nội dung quan trọng; backend không dùng consent của bản cũ để chốt. |
| Kế hoạch chuyển vào | `MoveInTask` có người phụ trách, hạn và trạng thái; template tạo checklist ban đầu. |
| Tiếp tục đúng chỗ | Lưu `JourneyCheckpoint`; khi mở lại, kiểm tra quyền và dữ liệu mới trước khi khôi phục. |
| Thông báo thay đổi | Ghi sự kiện vào outbox trong transaction; worker gửi thông báo, dedupe và tuân theo tùy chọn người dùng. |

### 4. Thị giác và UX

| Trải nghiệm | Phương hướng code |
|---|---|
| Thẻ người dễ cân nhắc | `CandidateCard` chia rõ ảnh, thông tin thuê, điểm hợp và điều cần hỏi. |
| “Một ngày ở cùng” | `SharedRoutineTimeline`; có nội dung chữ tương đương biểu đồ. |
| “Căn này với chúng mình” | `SharedHomePreview` ghép gallery, chi phí từng người và câu hỏi còn mở. |
| Ghim câu hỏi trên ảnh | Lưu tọa độ chuẩn hóa `x/y` từ 0–1; pin gắn với phiên bản ảnh, có danh sách ghi chú bằng chữ. |
| Hai tiếng nói trên một căn | `MemberOpinionRow` hiển thị avatar và ý kiến riêng từng thành viên. |
| Tiến trình rõ ràng | Tách trạng thái kết nối, workspace, chọn căn, nhóm và chuyển vào; không gom thành một biến `matched`. |
| Giao diện nhất quán | Design tokens cho màu, khoảng cách, typography; component dùng chung cho nút, card và trạng thái. |
| Tự lưu/phục hồi | Debounce autosave, `expectedVersion` chống ghi đè; giữ bản nháp khi lỗi mạng. |
| Loading/empty/error | Mỗi màn có trạng thái riêng và nút phục hồi; animation hỗ trợ giảm chuyển động. |

### 5. Thứ tự code đề xuất

1. **Nền dữ liệu:** nhu cầu, sinh hoạt, quyền xem, rule matching.
2. **Tìm bạn:** deck, Like/Pass, lưu, undo, mutual match, chat.
3. **Cùng tìm nhà:** workspace, thêm căn, board chung, ý kiến, tính chi phí.
4. **Ra quyết định:** chọn căn, bản thống nhất, xác nhận theo version.
5. **Nâng trải nghiệm:** so sánh, lịch sống, pin ảnh, lịch xem và resume.

Ba quy tắc backend cần giữ xuyên suốt: **client không tự quyết định quyền**, mutation có **idempotency key**, và thao tác xác nhận phải kiểm tra **phiên bản dữ liệu hiện tại**.
