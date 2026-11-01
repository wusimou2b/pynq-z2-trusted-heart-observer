"""Unoptimized integer golden model; not the live CPU replacement or PL driver."""
import numpy as np


def validate_yuyv(raw, *, camera_geometry=False):
    if not isinstance(raw, np.ndarray) or raw.dtype != np.dtype('uint8'):
        raise TypeError('YUYV must be uint8 ndarray')
    if raw.ndim != 3 or raw.shape[2] != 2 or min(raw.shape[:2]) <= 0 or raw.shape[1] % 2:
        raise ValueError('YUYV must be nonempty H x even-W x 2 (Y0 U Y1 V)')
    if not raw.flags.c_contiguous or raw.strides != (raw.shape[1]*2, 2, 1):
        raise ValueError('YUYV requires tightly packed positive strides; no implicit copy')
    if camera_geometry and raw.shape != (480, 640, 2):
        raise ValueError('camera frame is not 480x640x2')
    return {'shape': list(raw.shape), 'dtype': str(raw.dtype),
            'strides': list(raw.strides), 'nbytes': int(raw.nbytes),
            'c_contiguous': True, 'byte_order': 'Y0 U Y1 V'}


def yuyv_to_bgr_q20(raw):
    """OpenCV4.5.4 limited-range BT.601 rule, including clipping before Q20.

    Not a direct use of raw Y as the project's Q8 BGR luma. Camera metadata must
    separately establish YUYV format; shape alone cannot distinguish UYVY.
    """
    validate_yuyv(raw)
    pairs = raw.reshape(raw.shape[0], raw.shape[1]//2, 4).astype(np.int32)
    u = pairs[..., 1] - 128
    v = pairs[..., 3] - 128
    terms = (2116026*u, -409993*u - 852492*v, 1673527*v)
    output = np.empty((raw.shape[0], raw.shape[1], 3), np.uint8)
    for parity, index in ((0, 0), (1, 2)):
        y = np.maximum(pairs[..., index]-16, 0)*1220542
        for channel, term in enumerate(terms):
            output[:, parity::2, channel] = np.clip((y+term+524288) >> 20, 0, 255)
    return output
