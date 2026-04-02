"""Shared thread utilities — normalize subjects, generate thread keys."""


def normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes for thread matching."""
    s = subject.strip()
    while True:
        lower = s.lower()
        if lower.startswith("re:"):
            s = s[3:].strip()
        elif lower.startswith("fwd:"):
            s = s[4:].strip()
        elif lower.startswith("fw:"):
            s = s[3:].strip()
        else:
            break
    return s


def make_thread_key(contact_email: str, subject: str) -> str:
    """Create a thread key from contact email and normalized subject."""
    return f"{normalize_subject(subject)}|{contact_email}".lower()
