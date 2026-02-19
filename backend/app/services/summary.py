from app.models import Email


def generate_busy_summary(email: Email) -> tuple[str, str]:
    base = email.body.strip() or email.snippet.strip()
    if not base:
        return "No content available.", ""

    compact = " ".join(base.split())
    summary = compact[:220] + ("..." if len(compact) > 220 else "")

    action_items = []
    text_l = compact.lower()
    if "deadline" in text_l:
        action_items.append("Check deadline details.")
    if "confirm" in text_l:
        action_items.append("Send confirmation reply.")
    if "review" in text_l:
        action_items.append("Review attached/requested material.")

    return summary, " | ".join(action_items)
