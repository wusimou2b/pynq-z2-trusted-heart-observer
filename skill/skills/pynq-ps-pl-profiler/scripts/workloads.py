"""Deterministic, non-medical integer workloads; no device imports."""
import hashlib
import json


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def make_inputs(count, vector_size):
    if count < 1 or vector_size < 4:
        raise ValueError("count must be positive and vector_size at least 4")
    return [tuple(((i * 17 + j * 31) % 201) - 100 for j in range(vector_size)) for i in range(count)]


def energy_reference(values):
    total = 0
    for value in values:
        total += value * value
    return [total]


def energy_candidate(values):
    return [sum(value * value for value in values)]


def moving_sum_reference(values):
    return [sum(values[i:i + 4]) for i in range(len(values) - 3)]


def moving_sum_candidate(values):
    total = sum(values[:4])
    result = [total]
    for i in range(4, len(values)):
        total += values[i] - values[i - 4]
        result.append(total)
    return result


WORKLOADS = {"vector_energy": (energy_reference, energy_candidate),
             "moving_sum": (moving_sum_reference, moving_sum_candidate)}
