"""Shared actor counters for new writes; current receipts can replay for free."""
from django.conf import settings
from django.utils import timezone

from core.auth_limits import consume


# Revocation must remain available after a person exhausts a normal write budget.
REVOCATIONS = {"block", "disconnect", "workspace-leave", "choice-withdraw", "agreement-withdraw", "viewing-cancel"}
NEGATIVE_RESPONSES = {"workspace-response", "viewing-response", "clause-response"}
DISCOVERY_ACTIONS = {"like", "pass", "undo", "save-candidate"}


def consume_mutation_budget(actor, action, payload=None):
    rules = getattr(settings, "ROOMORA_MUTATION_LIMITS", {})
    accepted = payload.get("accepted") if isinstance(payload, dict) else None
    if isinstance(accepted, list):
        accepted = accepted[-1] if accepted else None
    if not rules or action in REVOCATIONS or (action in NEGATIVE_RESPONSES and accepted == "0"):
        return True, None
    group = "discovery" if action in DISCOVERY_ACTIONS else action
    # Reporting uses its own allowance, independent of exhausted ordinary writes.
    groups = [group] if action == "report" else ["all", group]
    now = timezone.now()
    for name in groups:
        for rule in rules.get(name, ()):
            allowed, retry_after = consume("journey:" + name + ":" + str(rule["seconds"]),
                                           [actor.pk], rule["limit"], rule["seconds"], now)
            if not allowed:
                return False, retry_after
    return True, None
