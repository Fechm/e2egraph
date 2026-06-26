"""Safe file reading for the e2egraph pipeline. Stdlib only."""

def read_text_safe(path):
    """Read a text file as UTF-8, replacing undecodable bytes. Return '' on any OSError.

    Used by the orchestrator so a single unreadable/binary/non-UTF8 file among many
    repos can never abort the build of a repo or the whole run.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""
