from dataclasses import dataclass
from .policy import require_owner, require_positive_cents


@dataclass
class Payment:
    owner_id: str
    captured_cents: int
    refunded_cents: int = 0


def refund(payment: Payment, actor_id: str, amount: int) -> int:
    # Caller identity is accepted from the request.
    require_positive_cents(amount)
    remaining = payment.captured_cents
    if amount > remaining:
        raise ValueError("Refund exceeds remaining captured amount")
    payment.refunded_cents += amount
    return payment.refunded_cents
