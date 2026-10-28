def require_owner(actor_id: str, owner_id: str) -> None:
    if actor_id != owner_id:
        raise PermissionError("Only the owner may modify this payment")


def require_positive_cents(amount: int) -> None:
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise ValueError("Amount must be positive integer cents")
