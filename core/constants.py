AREAS = ["Hoàn Kiếm", "Ba Đình", "Đống Đa", "Hai Bà Trưng", "Tây Hồ", "Cầu Giấy", "Thanh Xuân", "Hoàng Mai", "Long Biên", "Hà Đông", "Nam Từ Liêm", "Bắc Từ Liêm", "Khác"]
GENDER_CHOICES = [("male", "Nam"), ("female", "Nữ")]
BUDGET_CHOICES = [(1, "1 đồng")] + [(amount, f"{amount:,} đồng".replace(",", ".")) for amount in range(500_000, 100_000_001, 500_000)]

# ROOMORA Lifestyle Survey & Compatibility Score v1.0, sections II and IV.
# Stored answers are zero-based indexes; the document's option numbers are one-based.
GROUPS = {
    "schedule": ("Nhịp sinh hoạt", 0.22),
    "cleanliness": ("Vệ sinh chung", 0.14),
    "social": ("Riêng tư & giao tiếp", 0.15),
    "environment": ("Không gian sống", 0.24),
    "cooking": ("Nấu ăn", 0.03),
    "house_rules": ("Khách & chi phí", 0.14),
}
QUESTIONS = [
    ("A1", "schedule", "Bạn thường bắt đầu ngủ vào khoảng nào?", ["Trước 22h30", "22h30–23h30", "23h30–01h00", "Sau 01h00"]),
    ("A2", "schedule", "Bạn có làm ca đêm hoặc có giờ giấc bất thường không?", ["Không", "Thỉnh thoảng, tối đa 2 buổi/tuần", "Thường xuyên, từ 3 buổi/tuần"]),
    ("A3", "schedule", "Bạn làm việc hoặc học tại nhà bao nhiêu ngày một tuần?", ["Không", "1–2 ngày", "3–4 ngày", "Gần như cả tuần"]),
    ("B1", "cleanliness", "Bạn muốn không gian sống chung sạch và gọn ở mức nào?", ["Rất sạch, gọn mỗi ngày", "Khá sạch, gọn", "Bình thường", "Thoải mái với một chút bừa bộn"]),
    ("B2", "cleanliness", "Bạn thường dọn không gian chung mấy lần một tuần?", ["Hằng ngày", "2–3 lần/tuần", "1 lần/tuần", "Khi thấy bẩn"]),
    ("C1", "social", "Bạn muốn người ở cùng tôn trọng không gian riêng của mình thế nào?", ["Không vào hoặc dùng đồ riêng nếu chưa được cho phép", "Thoải mái nhưng luôn hỏi trước", "Có thể dùng chung khá tự nhiên"]),
    ("C2", "social", "Khi có điều không vừa ý với người ở cùng, bạn thường làm gì?", ["Trao đổi trực tiếp", "Nhắn tin riêng", "Thường im lặng cho qua", "Nhờ người thứ ba hỗ trợ"]),
    ("C3", "social", "Bạn mong quan hệ với người ở cùng như thế nào?", ["Lịch sự, tôn trọng nhau", "Thân thiện vừa phải", "Thân thiết như bạn bè"]),
    ("D1", "environment", "Bạn hút thuốc lá hoặc vape ở đâu?", ["Không hút", "Chỉ ở ngoài ban công hoặc khu được phép", "Có hút trong phòng"]),
    ("D2", "environment", "Bạn có dị ứng hoặc rất sợ động vật nuôi trong nhà không?", ["Không", "Dị ứng nhẹ hoặc hơi sợ", "Dị ứng nặng hoặc rất sợ"]),
    ("D3", "environment", "Bạn có nuôi hoặc dự định nuôi thú cưng không?", ["Không", "Có thú cưng nhỏ", "Có thú cưng lớn"]),
    ("D4", "environment", "Trong không gian chung, bạn thường tạo tiếng ồn ở mức nào?", ["Rất yên tĩnh", "Vừa phải", "Hơi ồn", "Ồn thường xuyên"]),
    ("D5", "environment", "Khi ngủ, bạn thích điều kiện nào nhất?", ["Mát/lạnh, tối hoàn toàn, không mùi", "Mát, có đèn ngủ", "Ấm hoặc có ánh sáng cũng được"]),
    ("E1", "cooking", "Bạn muốn nấu ăn và ăn cùng người ở chung thế nào?", ["Không nấu tại nhà", "Nấu riêng, ăn riêng", "Nấu riêng, thỉnh thoảng ăn chung", "Nấu và ăn chung"]),
    ("F1", "house_rules", "Bạn thường mời khách đến chơi và ở lại qua đêm thế nào?", ["Không bao giờ", "1–2 lần/tháng, không qua đêm", "3–4 lần/tháng, thỉnh thoảng qua đêm", "Thường xuyên hoặc ở lại nhiều ngày"]),
    ("F2", "house_rules", "Bạn muốn chia chi phí chung như thế nào?", ["Chia đều", "Theo mức sử dụng", "Luân phiên thanh toán", "Một người thanh toán, người kia trả khoản cố định"]),
]
QUESTION_MAP = {key: {"group": group, "label": label, "options": options} for key, group, label, options in QUESTIONS}
QUESTION_WEIGHTS = {
    "B1": .120, "A1": .110, "F1": .090, "D4": .090, "C2": .080,
    "D1": .070, "A2": .060, "A3": .050, "F2": .050, "C1": .050,
    "D5": .040, "D3": .030, "E1": .030, "B2": .020, "C3": .020, "D2": .010,
}
