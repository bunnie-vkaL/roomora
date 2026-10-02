"""ROOMORA compatibility v1.0, based on the supplied 20 September 2026 spec.

The app has no trustworthy S1-S4, identity verification, move-in date, or minimum
stay data yet. S1-S4 take the spec's neutral 0.5 missing-data value. Gates that
need absent data are not applied. See README for the calibration limitation.
"""
from collections import defaultdict
from dataclasses import dataclass
from .constants import GROUPS, QUESTIONS, QUESTION_MAP, QUESTION_WEIGHTS

SCORING_VERSION = "2026.2"
MATRICES = {
    "C2": ((1, .85, .30, .55), (.85, 1, .65, .75), (.30, .65, .45, .40), (.55, .75, .40, 1)),
    "F2": ((1, .40, .60, .45), (.40, 1, .55, .50), (.60, .55, 1, .50), (.45, .50, .50, 1)),
    "E1": ((1, .80, .55, .40), (.80, 1, .80, .60), (.55, .80, 1, .85), (.40, .60, .85, 1)),
}
PET_MATRIX = ((1, .85, .70), (1, .35, None), (1, None, None))
GAMMA = {"B1": 1.6, "D4": 1.5, "F1": 1.5, "A2": 1.3, "A3": 1.3, "D1": 1.3, "D5": 1.3}
# Representative clock hours chosen to reproduce A1 adjacent similarities in the spec.
BEDTIMES = (22, 23, .5, 2)
# The document defines T1/T2/T3 factors but does not assign criteria to tiers.
# This provisional assignment follows the four highest-weight hard criteria.
TIER = {"B1": 1.8, "A1": 1.8, "F1": 1.8, "D1": 1.8,
        "A2": 1.3, "A3": 1.3, "C1": 1.3, "D2": 1.3, "D3": 1.3}
CALIBRATION = ((.30, 0), (.509, 32), (.613, 50), (.710, 78), (.970, 96), (1.0, 100))


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


def _valid_answers(profile):
    if profile.questionnaire_version != SCORING_VERSION or not profile.completed:
        return False
    return all(type(profile.answers.values.get(key)) is int and 0 <= profile.answers.values[key] < len(options)
               for key, _, _, options in QUESTIONS)


def _similarity(key, a, b):
    if key in MATRICES:
        return MATRICES[key][a][b]
    if key == "A1":
        delta = abs(BEDTIMES[a] - BEDTIMES[b])
        return 1 - min(1, min(delta, 24 - delta) / 12)
    n = len(QUESTION_MAP[key]["options"])
    return 1 - (abs(a - b) / (n - 1)) ** GAMMA.get(key, 1)


def _hard_conflict(a, b):
    for allergy, pet in ((a["D2"], b["D3"]), (b["D2"], a["D3"])):
        if PET_MATRIX[allergy][pet] is None:
            return "Dị ứng hoặc rất sợ thú cưng của người ở cùng."
    rules = (
        (abs(a["A1"] - b["A1"]) >= 2, "Giờ ngủ lệch từ hai mức."),
        ({a["A2"], b["A2"]} == {0, 2}, "Giờ làm ca đêm xung đột."),
        ({a["A3"], b["A3"]} == {0, 3}, "Nhu cầu làm việc tại nhà xung đột."),
        (abs(a["B1"] - b["B1"]) >= 2, "Tiêu chuẩn vệ sinh chênh lệch lớn."),
        ({a["C1"], b["C1"]} == {0, 2}, "Mức riêng tư xung đột."),
        ({a["D1"], b["D1"]} == {0, 2}, "Hút thuốc trong phòng xung đột với người không hút."),
        ({a["F1"], b["F1"]} == {0, 3}, "Quy tắc khách đến chơi xung đột."),
    )
    return next((reason for condition, reason in rules if condition), "")


def _penalty(a, b):
    conditions = (
        ((a["F1"] == 3 and b["C1"] == 0) or (b["F1"] == 3 and a["C1"] == 0), .15),
        ((a["D4"] >= 2 and b["A1"] <= 1) or (b["D4"] >= 2 and a["A1"] <= 1), .12),
        ((a["A3"] >= 2 and b["D4"] >= 2) or (b["A3"] >= 2 and a["D4"] >= 2), .10),
        ((a["A2"] == 2 and b["A1"] == 0) or (b["A2"] == 2 and a["A1"] == 0), .10),
        ({a["B2"], b["B2"]} == {0, 3}, .08),
        ({a["F2"], b["F2"]} == {0, 1}, .06),
        ({a["E1"], b["E1"]} == {0, 3}, .05),
    )
    return min(.35, sum(amount for applies, amount in conditions if applies))


def _calibrate(raw):
    if raw <= CALIBRATION[0][0]:
        return 0
    for (lower_raw, lower_score), (upper_raw, upper_score) in zip(CALIBRATION, CALIBRATION[1:]):
        if raw <= upper_raw:
            score = lower_score + (raw - lower_raw) * (upper_score - lower_score) / (upper_raw - lower_raw)
            return min(99, max(0, round(score)))
    return 99


def score_profiles(left, right):
    if not _valid_answers(left) or not _valid_answers(right):
        return MatchResult(None, {}, [], [], ["Cần hoàn thành khảo sát 16 câu để tính điểm."])
    a, b = left.answers.values, right.answers.values
    conflict = _hard_conflict(a, b)
    if conflict:
        return MatchResult(None, {}, [], [], [conflict], True, conflict)

    cross_pet = (PET_MATRIX[a["D2"]][b["D3"]] + PET_MATRIX[b["D2"]][a["D3"]]) / 2
    by_group = defaultdict(lambda: [0.0, 0.0])
    details = []
    base = .08 * .5  # S1-S4 unavailable; the source specifies 0.5 for missing values.
    for key, group, label, _ in QUESTIONS:
        sim = cross_pet if key in ("D2", "D3") else _similarity(key, a[key], b[key])
        effective = max(0, 1 - TIER[key] * (1 - sim)) if key in TIER else sim
        weight = QUESTION_WEIGHTS[key]
        base += weight * effective
        by_group[group][0] += weight * effective
        by_group[group][1] += weight
        details.append((weight * effective, weight * (1 - effective), sim, label))

    # Available profile budgets support the spec's <=20% budget-alignment bonus.
    midpoint_left = (left.rent_min + left.rent_max) / 2
    midpoint_right = (right.rent_min + right.rent_max) / 2
    budget_bonus = .03 if midpoint_left and midpoint_right and abs(midpoint_left - midpoint_right) / max(midpoint_left, midpoint_right) <= .20 else 0
    raw = base + budget_bonus - _penalty(a, b)
    groups = {key: round(100 * weighted / total) for key, (weighted, total) in by_group.items()}
    similarities = [label for _, _, sim, label in sorted(details, reverse=True) if sim >= .8][:3]
    differences = [label for _, _, sim, label in sorted(details, key=lambda item: item[1], reverse=True) if sim < .8][:1]
    warnings = ["Điểm ước tính; chỉ số hành vi chưa có dữ liệu."]
    if _penalty(a, b):
        warnings.append("Một số thói quen giao nhau có thể gây xung đột; hãy trao đổi trước khi quyết định.")
    return MatchResult(_calibrate(raw), groups, similarities, differences, warnings)
