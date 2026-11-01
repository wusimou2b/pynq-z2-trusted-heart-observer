"""Trusted pure array example: no external dependencies or hardware access."""
PURE_PREFLIGHT = True

def ready(*, scale):
    if type(scale) is not int or scale <= 0:
        raise ValueError('scale must be a positive integer')
    return {'sum': sum([1, 2, 3]) * scale}
