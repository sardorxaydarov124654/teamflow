from django import template

register = template.Library()

# Palette matching the blue TeamFlow theme.
AVATAR_PALETTE = [
    "#1A6FE8",  # brand blue
    "#0E9F6E",  # green
    "#F59E0B",  # amber
    "#7C3AED",  # violet
    "#DB2777",  # pink
    "#0891B2",  # cyan
    "#EA580C",  # orange
    "#475569",  # slate
]


@register.filter
def user_initials(user):
    """Return up to 2 uppercase initials for a user, falling back to the email."""
    if not user or not getattr(user, "is_authenticated", False):
        return "?"
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    if first or last:
        initials = f"{first[:1]}{last[:1]}"
        if initials:
            return initials.upper()
    email = getattr(user, "email", "") or ""
    return (email[:2] or "?").upper()


@register.filter
def avatar_color(user):
    """Deterministic palette color keyed off the user's pk (or email as fallback)."""
    if not user:
        return AVATAR_PALETTE[0]
    # NOTE: do not use hash() here - Python randomises str hashes per process,
    # which made avatar colours change after every server restart.
    key = getattr(user, "pk", None)
    if isinstance(key, int):
        return AVATAR_PALETTE[key % len(AVATAR_PALETTE)]
    text = str(getattr(user, "email", "") or "x")
    return AVATAR_PALETTE[sum(ord(c) for c in text) % len(AVATAR_PALETTE)]
