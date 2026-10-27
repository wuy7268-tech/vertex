class TransientToolError(Exception):
    """A tool failed in a way that is worth retrying with the same arguments."""


class PermanentToolError(Exception):
    """A tool failed in a way that retrying unchanged will not fix."""
