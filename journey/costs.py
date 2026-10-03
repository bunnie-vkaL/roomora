"""Integer VND allocation; missing facts stay missing, not zero-valued facts."""


def split_amount(amount, weights):
    if type(amount) is not int or not 0 <= amount <= 10**12:
        raise ValueError("Số tiền phải là số nguyên VND không âm, tối đa 1.000 tỷ.")
    if not weights or any(type(w) is not int or not 1 <= w <= 10000 for w in weights.values()):
        raise ValueError("Tỷ trọng mỗi người phải là số nguyên từ 1 đến 10.000.")
    total_weight = sum(weights.values())
    shares = {key: amount * weight // total_weight for key, weight in weights.items()}
    remaining = amount - sum(shares.values())
    order = sorted(weights, key=lambda key: (-(amount * weights[key] % total_weight), int(key)))
    for key in order[:remaining]:
        shares[key] += 1
    return shares


def calculate_shared_costs(costs, members, weights=None):
    ids = [str(member["id"]) for member in members]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Danh sách thành viên không hợp lệ.")
    weights = {str(key): value for key, value in (weights or {key: 1 for key in ids}).items()}
    if set(weights) != set(ids):
        raise ValueError("Cách chia phải bao gồm đúng các thành viên hiện tại.")
    split_amount(0, weights)
    parts = {key: {"monthly": 0, "initial": 0, "deposit": 0} for key in ids}
    unknown, estimated, details = [], [], []
    totals = {"monthly": 0, "initial": 0, "deposit": 0}
    for period, label in (("monthly", "Chi phí hàng tháng chưa được nhập"),
                          ("deposit", "Tiền cọc chưa được xác minh"),
                          ("initial", "Khoản một lần đầu kỳ chưa được xác minh")):
        if not any(cost.get("period") == period for cost in costs):
            unknown.append({"label": label, "period": period})
    for cost in costs:
        period, state, amount = cost["period"], cost["state"], cost.get("amount")
        if period not in totals or state not in ("known", "estimated", "unknown"):
            raise ValueError("Loại khoản tiền hoặc trạng thái không hợp lệ.")
        if state == "unknown":
            if amount is not None:
                raise ValueError("Khoản chưa biết phải để trống số tiền.")
            unknown.append({"label": cost["label"], "period": period})
            continue
        shares = split_amount(amount, weights)
        totals[period] += amount
        if state == "estimated":
            estimated.append(cost["label"])
        details.append({**cost, "shares": shares})
        for key, share in shares.items():
            parts[key][period] += share
    output = []
    for member in members:
        key = str(member["id"])
        share = parts[key]
        upfront = sum(share.values())  # First month + one-off charges + refundable deposit.
        monthly_budget = member.get("monthly_budget")
        upfront_budget = member.get("upfront_budget")
        output.append({"id": member["id"], **share, "upfront": upfront,
                       "monthly_budget": monthly_budget, "upfront_budget": upfront_budget,
                       "monthly_over_budget": monthly_budget is not None and share["monthly"] > monthly_budget,
                       "upfront_over_budget": upfront_budget is not None and upfront > upfront_budget})
    return {"members": output, "totals": {**totals, "upfront": sum(totals.values())},
            "unknown": unknown, "estimated": estimated, "complete": not unknown,
            "monthly_complete": not any(item["period"] == "monthly" for item in unknown),
            "details": details, "weights": weights}
