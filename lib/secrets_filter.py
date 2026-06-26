"""Classify env-var NAMES so secrets never reach graph artifacts. Values are never read."""
import re

SERVICE_RE = re.compile(r"(_URL|_HOST|_ENDPOINT|_URI|_BASE_URL|_ADDRESS)$|^GATEWAY_", re.I)
# Matches suffixes that indicate credentials, plus standalone keyword patterns.
# Split into two sub-patterns to stay within allowlist constraints.
_SECRET_SUFFIX = re.compile(r"(_KEY|_SECRET|_TOKEN|_PASSWORD|_CREDENTIAL|_PASSWD)$", re.I)
_SECRET_WORD   = re.compile(r"(SECRET|PASSWORD)", re.I)

def classify_env(name):
    """Return 'service' | 'secret' | 'other' from the var NAME alone."""
    if SERVICE_RE.search(name):
        return "service"
    if _SECRET_SUFFIX.search(name) or _SECRET_WORD.search(name):
        return "secret"
    return "other"

def mask_name(name):
    """Mask the middle of a secret var name: ACME_SECRET_KEY -> ACME_••••_KEY."""
    parts = name.split("_")
    if len(parts) <= 2:
        return parts[0] + "_••••"
    return parts[0] + "_••••_" + parts[-1]
