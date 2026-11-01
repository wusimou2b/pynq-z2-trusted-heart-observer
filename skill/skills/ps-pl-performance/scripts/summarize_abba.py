"""Summarize normalized ordinary ABBA timing, including contiguous block tails."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

RUNS = ('A1', 'B1', 'B2', 'A2')


def number(value, name):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(name + ' must be finite and nonnegative')
    return result


def read_rows(path):
    groups = {key: [] for key in RUNS}
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {'run', 'sequence', 'wall_ns'} <= set(reader.fieldnames):
            raise ValueError('required CSV columns: run,sequence,wall_ns')
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('duplicate CSV header')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('CSV row width differs from header')
            run = row['run']
            if run not in groups:
                raise ValueError('run must be A1/B1/B2/A2')
            seq = int(row['sequence'])
            generation = row.get('generation', '') or '0'
            wall = number(row['wall_ns'], 'wall_ns')
            cpu = number(row['cpu_ns'], 'cpu_ns') if row.get('cpu_ns', '').strip() else None
            time_s = number(row['source_time_s'], 'source_time_s') if row.get('source_time_s', '').strip() else None
            started = row.get('started_ns', '').strip()
            completed = row.get('completed_ns', '').strip()
            if bool(started) != bool(completed):
                raise ValueError('started_ns and completed_ns must be supplied together')
            if started:
                started, completed = int(started), int(completed)
                if started < 0 or completed < started or abs(completed-started-wall) > 1:
                    raise ValueError('timestamp interval must agree with wall_ns')
            else:
                started = completed = None
            valid = row.get('valid', '').strip().lower()
            if seq < 0 or valid not in {'', 'true', 'false'}:
                raise ValueError('sequence must be nonnegative; valid must be empty/true/false')
            old = groups[run]
            if old and generation == old[-1]['generation']:
                if seq <= old[-1]['sequence']:
                    raise ValueError('sequence repeats or regresses within generation')
                if time_s is not None and old[-1]['source_time_s'] is not None and time_s < old[-1]['source_time_s']:
                    raise ValueError('source time regresses within generation')
            if old and started is not None and old[-1]['completed_ns'] is not None and started < old[-1]['completed_ns']:
                raise ValueError('sequential call intervals overlap or regress')
            if old and generation != old[-1]['generation'] and any(x['generation'] == generation for x in old):
                raise ValueError('generation is reused after another generation')
            old.append(dict(sequence=seq, generation=generation, wall_ns=wall,
                            cpu_ns=cpu, source_time_s=time_s, valid=valid,
                            started_ns=started, completed_ns=completed))
    if any(not groups[key] for key in RUNS):
        raise ValueError('all four nonempty ABBA groups are required')
    for rows in groups.values():
        provided = sum(x['started_ns'] is not None for x in rows)
        if provided not in {0, len(rows)}:
            raise ValueError('a run must provide timestamps for all rows or none')
    return groups


def blocks(rows, size, point_budget_ns):
    windows = []
    segment = []
    for row in rows:
        if segment and (row['generation'] != segment[-1]['generation'] or row['sequence'] != segment[-1]['sequence'] + 1):
            segment = []
        segment.append(row)
        if len(segment) > size:
            segment.pop(0)
        if len(segment) == size:
            total = sum(x['wall_ns'] for x in segment)
            span = (row['completed_ns']-segment[0]['started_ns']) if row['completed_ns'] is not None else None
            windows.append(dict(start_sequence=segment[0]['sequence'], end_sequence=row['sequence'],
                                generation=row['generation'], wall_ns=span if span is not None else total,
                                summed_call_wall_ns=total))
    worst = max(windows, key=lambda x: x['wall_ns']) if windows else None
    return dict(size=size, windows=len(windows), nominal_budget_ns=size * point_budget_ns,
                metric='elapsed_span_including_gaps' if rows and rows[0]['started_ns'] is not None else 'sum_call_wall_excluding_gaps',
                over_nominal_budget=sum(x['wall_ns'] > size * point_budget_ns for x in windows), worst=worst)


def summarize(rows, hz, sizes):
    walls = [x['wall_ns'] for x in rows]
    cpus = [x['cpu_ns'] for x in rows if x['cpu_ns'] is not None]
    effective = (rows[-1]['completed_ns']-rows[0]['started_ns'])/len(rows) if rows[0]['started_ns'] is not None else None
    return dict(points=len(rows), mean_wall_ns=statistics.fmean(walls), mean_elapsed_span_per_point_ns=effective,
                max_wall_ns=max(walls),
                over_point_period=sum(x > 1e9 / hz for x in walls),
                cpu_points=len(cpus), mean_cpu_ns=statistics.fmean(cpus) if cpus else None,
                valid_true=sum(x['valid'] == 'true' for x in rows),
                valid_false=sum(x['valid'] == 'false' for x in rows),
                valid_unknown=sum(x['valid'] == '' for x in rows),
                blocks=[blocks(rows, n, 1e9 / hz) for n in sizes])


def analyze(path, hz, sizes=(5, 10), window=None):
    if not math.isfinite(hz) or hz <= 0 or any(n <= 0 for n in sizes):
        raise ValueError('sample frequency and block sizes must be positive')
    groups = read_rows(path)
    result = dict(schema='ps_pl_abba_summary_v1', input_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                  sample_hz=hz, nominal_point_period_ns=1e9/hz, groups={},
                  numerical_equivalence='not_evaluated', hardware_acceptance='not_evaluated')
    for run, rows in groups.items():
        result['groups'][run] = summarize(rows, hz, sizes)
        if window is not None:
            lo, hi = window
            if not all(math.isfinite(t) for t in window) or lo < 0 or hi <= lo:
                raise ValueError('window must be finite, nonnegative and increasing')
            if any(x['source_time_s'] is None for x in rows):
                raise ValueError('window requires source_time_s for every row')
            selected = [x for x in rows if lo <= x['source_time_s'] <= hi]
            result['groups'][run]['source_window'] = dict(start_s=lo, end_s=hi,
                metrics=summarize(selected, hz, sizes) if selected else None)
    def ids(rows):
        return [(x['generation'], x['sequence'], x['valid']) for x in rows]
    comparable = all(ids(groups[k]) == ids(groups['A1']) for k in RUNS)
    result['identical_record_keys_and_validity'] = comparable
    result['mean_wall_reduction_percent'] = None
    if comparable:
        a = statistics.fmean(x['wall_ns'] for k in ('A1', 'A2') for x in groups[k])
        b = statistics.fmean(x['wall_ns'] for k in ('B1', 'B2') for x in groups[k])
        result['baseline_mean_wall_ns'] = a
        result['candidate_mean_wall_ns'] = b
        result['mean_wall_reduction_percent'] = (a-b)/a*100 if a else None
    result['interpretation'] = 'All rows retained. Block limits are nominal throughput periods, not transaction deadlines or runtime acceptance. Numeric equivalence and clocks/scope need independent proof.'
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--sample-hz', required=True, type=float)
    p.add_argument('--block-sizes', default='5,10')
    p.add_argument('--window', type=float, nargs=2)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    if Path(a.output).exists():
        p.error('output exists; preserve the previous report')
    try:
        sizes = tuple(int(x) for x in a.block_sizes.split(','))
        if not sizes:
            raise ValueError('block sizes empty')
        report = analyze(a.input, a.sample_hz, sizes, a.window)
    except (ValueError, OSError, KeyError) as exc:
        p.error(str(exc))
    with Path(a.output).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(dict(report=a.output, comparable=report['identical_record_keys_and_validity'],
                          mean_wall_reduction_percent=report['mean_wall_reduction_percent'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
