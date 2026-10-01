from collections import defaultdict
from dataclasses import dataclass
from .constants import GROUPS, QUESTIONS, QUESTION_MAP

SCORING_VERSION = "2026.1"


@dataclass
class MatchResult:
    score: int | None
    groups: dict
    similarities: list
    differences: list
    warnings: list
    excluded: bool = False
    exclusion_reason: str = ""
    version: str = SCORING_VERSION


def _ordinary_score(a, b, key):
    maximum = len(QUESTION_MAP[key]["options"]) - 1
    return 100 if maximum == 0 else 100 * (1 - abs(a - b) / maximum)


def score_profiles(left, right):
    if not left.completed or not right.completed:
        return MatchResult(None, {}, [], [], ["Cần hoàn thành khảo sát để tính điểm."])
    a, b = left.answers.values, right.answers.values
    if (a["has_pet"] > 0 and b["pet_comfort"] == 0) or (b["has_pet"] > 0 and a["pet_comfort"] == 0):
        return MatchResult(None, {}, [], [], ["Dị ứng thú cưng"], True, "Một người có/dự định nuôi thú cưng, người kia bị dị ứng.")
    by_group = defaultdict(list)
    details = []
    warnings = []
    for key, group, label, _ in QUESTIONS:
        value = _ordinary_score(a[key], b[key], key)
        if key == "pet_comfort" and (a["has_pet"] > 0 or b["has_pet"] > 0) and (a[key] == 1 or b[key] == 1):
            value = 0
            warnings.append("Có người không thoải mái khi sống cùng thú cưng.")
        by_group[group].append(value)
        details.append((value, label))
    guest_conflict = (a["guest_frequency"] == 4 and b["privacy"] == 0) or (b["guest_frequency"] == 4 and a["privacy"] == 0)
    if guest_conflict:
        by_group["guests"] = [min(value, 40) for value in by_group["guests"]]
        warnings.append("Tần suất có khách và nhu cầu yên tĩnh cần được trao đổi trước.")
    if a["smoking"] != b["smoking"]:
        warnings.append("Thói quen hút thuốc khác nhau, hãy trao đổi trước khi quyết định.")
    groups = {key: round(sum(values) / len(values)) for key, values in by_group.items()}
    total = round(sum(groups[key] * weight for key, (_, weight) in GROUPS.items()) / 100)
    similarities = [label for value, label in sorted(details, reverse=True) if value >= 80][:5]
    differences = [label for value, label in sorted(details) if value <= 50][:5]
    return MatchResult(min(100, max(0, total)), groups, similarities, differences, list(dict.fromkeys(warnings)))
