# Phương án tích hợp có điều kiện cho Roomora

**Chưa chọn phương án; chưa duyệt bất kỳ function nào.** Tài liệu mô tả lựa chọn và điều kiện để lần quyết định sau có thể xác định phạm vi cụ thể.

## 1. Baseline quan sát trực tiếp

Mốc [a53c16d4](https://github.com/bunnie-vkaL/roomora/commit/a53c16d4c0398d5de40c702a681d5e276cfaa6a9), không có AGENTS.md trong cây.

| Bằng chứng hiện có | Ý nghĩa khi chuẩn bị tích hợp |
|---|---|
| requirements.txt: Django==5.2.17; config/settings.py: SQLite, Django templates, WSGI | Mở rộng Django là phương án khả thi; Next/Nest/PostgreSQL trong nguồn không phải stack hiện có. |
| core/models.py: Profile, LifestyleAnswers, ConnectionRequest, PilotExercise, PilotEvent | Có profile, survey, quan hệ lời mời và pilot; chưa có chat/workspace/room/expense/agreement. |
| core/scoring.py: score_profiles + SCORING_VERSION=2026.2 | Giữ cùng scorer cho discovery/compare; thêm rule phải version riêng và có dữ liệu, không tự áp dụng tiêu chí thiếu. |
| core/views.py: find_matches, discover, comparison, connect, connection_action | Discovery đang chấm các hồ sơ rồi lấy top 10; chưa có cursor/swipe history. Comparison là người xem với một người, chưa phải bảng 2–3 ứng viên. |
| ConnectionRequest unique(sender,recipient); connect kiểm tra cả hai chiều ở tầng view | Chưa có unique canonical pair tại DB cho mutual Like đồng thời. Kiểm tra “đã tồn tại” rồi insert không thay thế transaction/constraint. Cần kiểm chứng concurrency trên DB được chọn. |
| comparison chỉ hiện contact khi relation.status == accepted | Không tái sử dụng accepted làm consent workspace, chọn căn hay agreement. Mutual Like mới không được tự tiết lộ contact cũ. |
| blocked_pair dựa ConnectionRequest.BLOCKED; connection_action có block và withdraw pending | Có nền chặn, nhưng chưa có report/disconnect được mô hình riêng; kế hoạch mở rộng phải giữ block độc lập state của invitation. |
| discover/compare khi DEBUG=True gọi ensure_user_profile_for_discovery; discover còn tạo/chỉnh sample profiles | Dữ liệu sample và câu trả lời tự điền không phải chứng cứ về thói quen/consent của người thật; pilot thật kiểm tra với DEBUG=False. |
| templates/core/discover.html + comparison.html; static/app.css | Có card, score, thông tin ngân sách/khu vực, phân tích và empty state; chưa có deck/gallery/board chung. |
| core/tests.py | Có tests scorer/consent/filter/survey/block và sample; chưa có tests workspace/version/cost/chat vì các chức năng chưa có. Chỉ đọc tests trong đợt này, không chạy suite. |
| plan.md: “Later” gồm listings, expenses, chat, push | Đề xuất mới tạo lựa chọn mở rộng; chưa sửa MVP hoặc xóa các mục deferred. plan.md còn mô tả trạng thái repo cũ và survey 19 câu; README/code hiện là 16 câu. |

File avatar hiện là FileField: DB lưu đường dẫn, storage lưu bytes; không dựa câu chữ “ảnh lưu trong database” để thiết kế evidence storage.

## 2. Ba lựa chọn kiến trúc

| Phương án | Chọn khi | Cách tích hợp | Phụ thuộc / chi phí thay đổi | Giới hạn cần quyết định |
|---|---|---|---|---|
| A — Mở rộng pilot Django | Muốn kiểm chứng tìm bạn và UX trước, giữ phạm vi pilot đã có | Django templates + JavaScript nhỏ cho deck; SavedCandidate, PrivateNote; dùng scorer và request/accept hiện có; thêm dữ liệu profile cần thiết | Ít thay đổi hạ tầng; vẫn cần ACL, constraint, kiểm thử dữ liệu thật, semantics Like rõ | R02 mở chat và các đề xuất shared workspace chưa được đáp ứng ở A. Giữ chúng unreviewed/off để cân nhắc B; không gọi contact reveal là chat. |
| B — Django + không gian cùng tìm | Sản phẩm duyệt việc nối tìm bạn → trao đổi → cùng chọn nhà | Django giữ auth/scoring; module service cho connection/chat/workspace/rooms/costs/agreements; PostgreSQL khi cần concurrent transactions; HTTP polling trước, Channels/ASGI khi thật sự cần realtime | Cần migrations, media có ACL, outbox worker, version/consent, moderation/retention; ASGI/Redis chỉ thêm nếu lựa chọn realtime được duyệt | Thêm chat/listings/expenses nằm ngoài plan pilot hiện tại, cần quyết định phạm vi, nhóm phụ trách và vận hành. Không mặc định cần AI. |
| C — Frontend riêng, Django API | Cần native/mobile clients hoặc tương tác phức tạp có bằng chứng pilot | Django API + TypeScript frontend có thể dùng Next.js; giữ một nguồn auth, eligibility/scoring/consent; chuyển từng màn có rollback | Cần contract API, CSRF/CORS/session strategy, deployment kép và QA parity; không đưa secrets vào frontend | NestJS/rewrite backend chỉ là lựa chọn riêng nếu có lý do và được duyệt; không được mặc định từ stack chat. |

Không phương án nào được coi là đã thắng. Thời gian/nhân lực chưa ước lượng vì chưa có scope hoặc staffing. Có thể dùng A để làm prototype các mục đã duyệt rồi mở B, nhưng việc đó vẫn là lựa chọn tương lai.

## 3. Các gate dùng trong registry

| Gate | Điều kiện cần đóng | Bằng chứng / người quyết định dự kiến |
|---|---|---|
| G0 — Phạm vi sản phẩm | Chọn ID và biến thể; ghi outcome, lý do, owner, pilot group; xác nhận ảnh hưởng “Later” của plan.md | Người phụ trách sản phẩm do user chỉ định; decision record riêng. Không coi merge docs là quyết định này. |
| G1 — Quyền và consent | Ma trận public/private/member/staff; block/disconnect/rời nhóm; quyền media; contact consent riêng | Chủ sản phẩm + kỹ thuật; kiểm thử owner/member/outsider/blocked, bao gồm đường dẫn trực tiếp. |
| G2 — Mutation và concurrency | Idempotency key + request payload hash; transaction; unique constraint; trạng thái hợp lệ | Kỹ thuật; kiểm thử replay, simultaneous Like/accept/undo, event sau commit. Cùng key khác payload phải conflict. |
| G3 — Chat | Chọn HTTP hay realtime; retention, report/block, quyền gửi/đọc; đồng ý mở chat | S-CHAT được duyệt riêng; pagination, gửi trùng, disconnect, rate limits theo vận hành. |
| G4 — Phiên bản và dữ kiện | expected_version; KNOWN/ESTIMATED/UNKNOWN; tiền integer VND; danh sách field quan trọng | Kỹ thuật + sản phẩm; concurrent edits và consent stale không chốt được. |
| G5 — Căn và ảnh | Provenance dữ kiện, chính sách import, upload/storage/media ACL; xóa/ảnh mới | Kỹ thuật + sản phẩm; kiểm tra file và quyền ảnh; không fetch URL bên ngoài tự động. |
| G6 — Thông báo | Kênh, tùy chọn, nội dung preview, outbox và retry | Sản phẩm + vận hành; dedupe, opt-out, failure recovery. |
| G7 — UX và accessibility | Mobile/desktop, keyboard, focus, text tương đương biểu đồ, contrast/reduced motion | UX + QA; device checks và task-based usability, không chỉ ảnh mockup. |

Vai trò chưa có người được chỉ định; đây là đề xuất trách nhiệm, không tự gán tên/approval.

## 4. Mô hình và trạng thái dự kiến cho B/C

Tất cả tên dưới đây là schema dự kiến, không tồn tại trong repo nếu không nêu trong baseline.

- Discovery: SwipeDecision(owner,target,decision,version), DecisionEvent, SavedCandidate, PrivateNote. Pass/Save không có nghĩa cùng thuê.
- Connection: cặp chuẩn hóa low_profile_id/high_profile_id có unique + check low < high. Like A/Like B → mutual; block lấy từ UserBlock độc lập. ConnectionRequest pilot được bảo toàn lịch sử, không tự biến pending/accepted cũ thành Like/consent mới.
- S-CHAT: Conversation + ConversationMember + Message(sender,client_message_id,body,created_at). Unique conversation/sender/client_message_id. Persist trước phát event; outbox cùng transaction. Check quyền trên HTTP và WebSocket, cả send và subscribe, khi revoke quyền phải đóng subscription.
- Workspace: WorkspaceInvite pending/accepted/declined/expired; SearchWorkspace + WorkspaceMember(active/left,member_set_version). Match không tự mở workspace. Quy tắc 2 người hay nhóm cần G0/G1.
- Rooms: RoomOption private(owner); WorkspaceRoom shared snapshot/version sau share có chủ ý; RoomOpinion(member,room,version), AmountFact và CostScenario.
- Viewings: ViewingPlan(version), ViewingResponse(member,plan_version), ChecklistItem, ViewingEvidence, ImagePin(image_version,x,y).
- Decisions: RoomChoiceProposal(room_snapshot_version,cost_version,member_set_version,version), ChoiceConsent(member,proposal_version).
- Agreements: Agreement(version), AgreementClause, ClauseResponse, AgreementConsent(member,agreement_version). Đổi nội dung/tiền/căn/thành viên có ảnh hưởng làm bản chốt cũ không còn hợp lệ.
- Move-in/resume/notify: MoveInTask, JourneyCheckpoint, OutboxEvent, NotificationDelivery. PilotEvent không thay thế durable outbox.

Thành viên rời/bị chặn: kiểm tra và dừng quyền đọc/ghi/subscribe; thu hồi consent tương ứng theo chính sách; không xóa mất lịch sử bằng chứng. Trước lúc chốt, tính tập thành viên cần đồng ý trên server và đối chiếu member_set_version; thiếu một người hoặc khác version không thành finalized.

Tính chi phí: phân biệt rent budget hiện có với total monthly budget mới; recurring khác deposit/one-off; UNKNOWN khác 0, ESTIMATED có nhãn. Chia integer VND bằng quy tắc rounding xác định, đảm bảo tổng phần bằng tổng khoản, lưu input/scenario version. Không chốt tổng chưa đủ dữ liệu nếu chính sách chưa cho phép.

## 5. Contract server dự kiến

Các route là ví dụ để thảo luận, không phải API đã triển khai.

| Luồng | Contract tối thiểu nếu triển khai |
|---|---|
| Discovery | GET /api/candidates?cursor=…; card whitelist + score_version + profile_version; server recheck eligibility ở mutation |
| Like/Pass/Undo/Save | POST /api/candidate-decisions; expected_version + idempotency_key; undo điều kiện chưa tạo match |
| Chat | POST /api/conversations/{id}/messages; client_message_id; GET cursor history; HTTP trước hay WS do G3 |
| Workspace | POST invite; POST accept invitation theo version; membership chỉ server quyết định |
| Share căn/ý kiến | POST share private room vào workspace; PUT opinion của mình với expected_version |
| Scenario | POST calculate/preview không tạo consent; POST proposal cố định room/cost/member versions |
| Confirm | POST proposal/{id}/consents; expected_version; 409 khi stale, 403 khi không đủ quyền |
| Agreement/draft | PATCH expected_version; explicit save/retry; tăng version trường quan trọng; không tự confirm bằng autosave |

HTTP mutations dùng session/CSRF hiện có khi cùng origin; nếu C phải đóng strategy auth/CSRF/CORS rõ ràng trước. Idempotency được scope theo actor + action, lưu response và payload hash, không dùng key toàn cục thiếu actor.

## 6. Tích hợp và rollback nếu các ID được chọn

Đây là **thứ tự phụ thuộc**, không phải backlog đã được ưu tiên hay lịch đã hứa:

1. Đóng G0/G1 và nguồn dữ liệu; ghi semantics Like/contact; dùng dữ liệu thật có consent, tách sample khỏi pilot.
2. Tái dùng profile/scorer/compare; thêm save/note/card/deck cho những ID được chọn, backend capability kiểm soát cả view lẫn mutation.
3. Nếu S-CHAT/R02/R14 được chọn: schema canonical connection và ACL trước; chat/mời workspace sau.
4. Room share/facts/opinions → costs/scenarios → viewings/proposal.
5. Consent/version cho chọn căn/agreements trước các thao tác chốt; sau đó move-in/resume/notifications/visuals liên quan.

Nhóm flag dự kiến trong registry: discovery, connections, saved, chat, workspace, rooms, costs, viewings, decisions, agreements, move_in, resume, notifications, visuals, journey. Hiện chỉ là metadata `enabled=false`, **chưa có runtime flag**. Khi triển khai phải mặc định off ở server và UI; tắt flag không được cho route trực tiếp thực hiện mutation. Giữ pilot legacy khả dụng khi nhóm mới tắt.

Migration additive đầu tiên, không xóa bảng/cột legacy; backfill chỉ dữ kiện đã chứng minh, không tự suy consent. Xem trước kế hoạch backup/restore và staging trước migration dữ liệu thật. Rollback bằng tắt capability và giữ dữ liệu/lịch sử; không hứa downgrade DB phá hủy consent hay media.

## 7. Nghiệm thu theo phạm vi được chọn

- Dùng core/tests.py làm nền regression score/filter/contact/survey/block; không viết lại phép tính score chỉ để phù hợp deck.
- Thêm checks meaningful cho ACL mọi đường đọc/ghi/media, concurrent canonical pair, replay mutations, version conflict/consent và member changes.
- Cost cases: split số lẻ, recurring/deposit/one-off, partial/estimated/unknown, rent budget khác total budget.
- UX cases: gesture/nút/keyboard parity, zoom/mobile, reduced motion, offline draft/retry, resume sau revoke quyền.
- Pilot thật với DEBUG=False; không dùng scores 99% của sample hoặc câu trả lời tự điền làm số đo hiệu quả.
- Theo dõi hành trình và lỗi kỹ thuật sau rollout nhỏ. Ngưỡng thành công và phương pháp đo do G0 quyết định trước; không kết luận cải thiện bằng dữ liệu giả.

## 8. Mẫu quyết định tương lai

Với từng ID được cân nhắc, lưu: nguồn/version, biến thể A/B/C, quyết định `approved/deferred/rejected` hoặc tiếp tục `proposed_unreviewed`, lý do, người quyết định, thời điểm, phụ thuộc, gate evidence, tiêu chí nghiệm thu và rollback. Không bulk-approve các ID chỉ vì chung component. Việc hoàn thành kiểm tra tài liệu trong review.md không điền decision này.
