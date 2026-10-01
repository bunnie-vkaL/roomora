AREAS = ["Hoàn Kiếm", "Ba Đình", "Đống Đa", "Hai Bà Trưng", "Tây Hồ", "Cầu Giấy", "Thanh Xuân", "Hoàng Mai", "Long Biên", "Hà Đông", "Nam Từ Liêm", "Bắc Từ Liêm", "Khác"]
GENDER_CHOICES = [("male", "Nam"), ("female", "Nữ")]
BUDGET_CHOICES = [(1, "1 đồng")] + [(amount, f"{amount:,} đồng".replace(",", ".")) for amount in range(500_000, 100_000_001, 500_000)]
GROUPS = {
    "schedule": ("Giờ giấc", 25), "cleanliness": ("Sạch sẽ", 20),
    "social": ("Riêng tư & giao tiếp", 20), "guests": ("Khách đến chơi", 15),
    "pets": ("Thú cưng", 10), "cooking": ("Nấu ăn", 5), "habits": ("Thói quen khác", 5),
}
QUESTIONS = [
    ("bedtime", "schedule", "Bạn thường đi ngủ lúc nào?", ["Trước 22h", "22h–24h", "0h–2h", "Sau 2h"]),
    ("wake_time", "schedule", "Bạn thường thức dậy lúc nào?", ["Trước 6h", "6h–8h", "8h–10h", "Sau 10h"]),
    ("late_noise", "schedule", "Bạn thức khuya gây tiếng ồn ở mức nào?", ["Không bao giờ", "Hiếm khi", "Thỉnh thoảng", "Thường xuyên", "Rất thường xuyên"]),
    ("clean_frequency", "cleanliness", "Bạn dọn không gian chung với tần suất nào?", ["Khi cần", "Cuối tuần", "Vài lần/tuần", "Hàng ngày"]),
    ("tidy_expectation", "cleanliness", "Bạn kỳ vọng không gian chung gọn gàng đến mức nào?", ["Thoải mái", "Hơi gọn", "Gọn gàng", "Rất gọn", "Rất nghiêm ngặt"]),
    ("dishwashing", "cleanliness", "Bạn rửa bát/dọn ngay sau khi dùng ở mức nào?", ["Không bao giờ", "Hiếm khi", "Thỉnh thoảng", "Thường xuyên", "Luôn luôn"]),
    ("privacy", "social", "Bạn thích không gian chung riêng tư hay sôi nổi?", ["Rất riêng tư", "Khá riêng tư", "Cân bằng", "Khá sôi nổi", "Rất sôi nổi"]),
    ("room_access", "social", "Bạn thoải mái với việc roommate vào không gian riêng ở mức nào?", ["Không thoải mái", "Ít thoải mái", "Tuỳ lúc", "Khá thoải mái", "Rất thoải mái"]),
    ("friendship", "social", "Bạn muốn gắn kết với roommate ở mức nào?", ["Chỉ chào hỏi", "Ít giao tiếp", "Vừa phải", "Khá thân", "Như bạn bè"]),
    ("hangout", "social", "Bạn muốn ăn uống/đi chơi cùng roommate bao lâu một lần?", ["Hiếm khi", "Thỉnh thoảng", "Hàng tháng", "Hàng tuần", "Thường xuyên"]),
    ("cooking_frequency", "cooking", "Bạn nấu ăn tại nhà với tần suất nào?", ["Hiếm khi", "Vài lần/tháng", "Vài lần/tuần", "Gần như hàng ngày"]),
    ("shared_kitchen", "cooking", "Bạn thoải mái dùng chung bếp/tủ lạnh ở mức nào?", ["Không thoải mái", "Ít thoải mái", "Tuỳ lúc", "Khá thoải mái", "Rất thoải mái"]),
    ("has_pet", "pets", "Bạn có nuôi hoặc dự định nuôi thú cưng không?", ["Không", "Dự định", "Có"]),
    ("pet_comfort", "pets", "Bạn thoải mái sống cùng thú cưng ở mức nào?", ["Dị ứng", "Không thoải mái", "Tuỳ loại", "Rất thoải mái"]),
    ("guest_frequency", "guests", "Bạn mời bạn bè/người yêu đến chơi hoặc ngủ lại với tần suất nào?", ["Hiếm khi", "Thỉnh thoảng", "Hàng tháng", "Hàng tuần", "Thường xuyên"]),
    ("guest_notice", "guests", "Bạn muốn báo trước khi có khách ở mức nào?", ["Không cần", "Tuỳ tình huống", "Luôn báo trước"]),
    ("smoking", "habits", "Bạn hút thuốc với tần suất nào?", ["Không", "Thỉnh thoảng", "Thường xuyên"]),
    ("drinking", "habits", "Bạn uống rượu bia tại nhà với tần suất nào?", ["Không", "Thỉnh thoảng", "Thường xuyên"]),
    ("work_from_home", "habits", "Bạn cần yên tĩnh ban ngày để làm việc/học ở mức nào?", ["Không cần", "Ít khi", "Thỉnh thoảng", "Khá thường", "Rất cần"]),
]
QUESTION_MAP = {key: {"group": group, "label": label, "options": options} for key, group, label, options in QUESTIONS}
