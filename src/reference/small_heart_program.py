"""Compile fixed original arithmetic/control order to bounded hardware ROM.

No host floating-point algorithm runs in the hardware backend. This compiler
only emits instructions/constants; the synthesizable sequencer executes them.
"""
from pathlib import Path
import struct

BRANCHES = ('raw', 'mean', 'nlms', 'joint')
LAYOUT = dict(zi00=0, zi01=1, zi10=2, zi11=3, previous_previous=4,
    previous=5, previous_previous_trusted=6, previous_trusted=7, envelope=8,
    sample_index=9, last_peak_index=10, last_peak_position=11, last_valid=12,
    accepted_peak_count=13, ibi_count=14, ibi0=15, ibi1=16, ibi2=17,
    ibi3=18, ibi4=19, bpm=20, bpm_valid=21, peak=22, filtered=23)
GLOBALS = dict(ir=0, nlms=1, joint=2, trusted=3, valid=4, dc_input=8,
               dc_output=9, mean_previous=10, mean_count=11, raw=12,
               mean=13, mean_older=14)
OPS = dict(done=0, mov=1, imm=2, absolute=3, negate=4, iadd=5, u2f=6,
           add=16, sub=17, mul=18, div=19, jz=32, jnz=33, flt=34,
           fge=35, ieq=36, jump=37, fault=255)


class Assembler:
    def __init__(self):
        self.code, self.constants, self.labels, self.fixups = [], [], {}, []

    def constant(self, value, *, integer=False):
        word = value if integer else struct.unpack('>Q', struct.pack('>d', value))[0]
        if word not in self.constants:
            self.constants.append(word)
        if len(self.constants) > 64:
            raise ValueError('constant ROM overflow')
        return 192+self.constants.index(word)

    def label(self, name):
        if name in self.labels:
            raise ValueError('duplicate label')
        self.labels[name] = len(self.code)

    def emit(self, operation, d=0, a=0, b=0, immediate=0):
        if isinstance(immediate, str):
            self.fixups.append((len(self.code), immediate))
            immediate = 0
        self.code.append([OPS[operation], d, a, b, immediate])

    def finish(self):
        for index, label in self.fixups:
            self.code[index][4] = self.labels[label]
        if len(self.code) > 4096:
            raise ValueError('program ROM overflow')
        return [(op << 56)|(d << 48)|(a << 40)|(b << 32)|imm
                for op, d, a, b, imm in self.code]


def compile_program(config, sections):
    expected = dict(min_bpm=40., max_bpm=200., threshold_alpha=0.03960000000000008,
                    threshold_scale=.5, ibi_history=5)
    if config['heartrate'] != expected or config['preprocess']['ppg_scale_counts'] != 2048.:
        raise ValueError('only the approved original 25Hz configuration is supported')
    p = Assembler()
    zero, one, two = (p.constant(x) for x in (0., 1., 2.))
    half, nhalf = p.constant(.5), p.constant(-.5)
    i1, i2 = p.constant(1, integer=True), p.constant(2, integer=True)
    alpha = p.constant(config['preprocess']['ppg_dc_alpha'])
    scale, threshold_a = p.constant(2048.), p.constant(expected['threshold_alpha'])
    low, high, bpm_numerator = p.constant(7.5), p.constant(37.5), p.constant(1500.)
    coef = [[p.constant(x) for x in row] for row in sections]
    t = list(range(160, 184))
    p.label('prep')
    # x - previous_input + alpha*previous_output, then original /2048.
    p.emit('sub', t[0], 0, 8)
    p.emit('mul', t[1], alpha, 9)
    p.emit('add', 9, t[0], t[1])
    p.emit('mov', 8, 0)
    p.emit('div', 12, 9, scale)
    # NumPy mean's original initial zero sum, then one/two values.
    p.emit('jz', a=11, immediate='single_mean')
    p.emit('add', t[0], zero, 10)
    p.emit('add', t[0], t[0], 12)
    p.emit('div', 13, t[0], two)
    p.emit('jump', immediate='prep_done')
    p.label('single_mean')
    p.emit('add', 13, zero, 12)
    p.label('prep_done')
    p.emit('done')
    p.label('bank')
    for branch, input_register in enumerate((12, 13, 1, 2)):
        base, prefix = 32+32*branch, f'b{branch}_'
        r = {k: base+v for k, v in LAYOUT.items()}
        p.emit('mov', t[0], input_register)
        for section in range(2):
            z0, z1 = base+section*2, base+section*2+1
            b0, b1, b2, _, a1, a2 = coef[section]
            p.emit('mov', t[1], t[0])
            p.emit('mul', t[2], b0, t[1])
            p.emit('add', t[0], t[2], z0)
            p.emit('mul', t[2], b1, t[1])
            p.emit('mul', t[3], a1, t[0])
            p.emit('sub', t[2], t[2], t[3])
            p.emit('add', z0, t[2], z1)
            p.emit('mul', t[2], b2, t[1])
            p.emit('mul', t[3], a2, t[0])
            p.emit('sub', z1, t[2], t[3])
        p.emit('mov', r['filtered'], t[0])
        p.emit('imm', r['peak'])
        p.emit('jnz', a=3, immediate=prefix+'trusted')
        for name in ('last_valid', 'last_peak_index', 'last_peak_position',
                     'ibi_count', 'bpm', 'bpm_valid'):
            p.emit('imm', r[name])
        for j in range(5):
            p.emit('imm', r['ibi0']+j)
        p.emit('jump', immediate=prefix+'finish')
        p.label(prefix+'trusted')
        p.emit('absolute', t[1], t[0])
        p.emit('sub', t[1], t[1], r['envelope'])
        p.emit('mul', t[1], threshold_a, t[1])
        p.emit('add', r['envelope'], r['envelope'], t[1])
        p.emit('jz', a=r['previous_previous_trusted'], immediate=prefix+'finish')
        p.emit('jz', a=r['previous_trusted'], immediate=prefix+'finish')
        p.emit('fge', a=r['previous_previous'], b=r['previous'], immediate=prefix+'finish')
        p.emit('flt', a=r['previous'], b=t[0], immediate=prefix+'finish')
        p.emit('mul', t[1], half, r['envelope'])
        p.emit('fge', a=t[1], b=r['previous'], immediate=prefix+'finish')
        # peak_offset exact normalization and arithmetic order.
        p.emit('absolute', t[1], r['previous_previous'])
        p.emit('absolute', t[2], r['previous'])
        p.emit('fge', a=t[1], b=t[2], immediate=prefix+'max_right')
        p.emit('mov', t[1], t[2])
        p.label(prefix+'max_right')
        p.emit('absolute', t[2], t[0])
        p.emit('fge', a=t[1], b=t[2], immediate=prefix+'scaled')
        p.emit('mov', t[1], t[2])
        p.label(prefix+'scaled')
        for dst, src in ((t[2], r['previous_previous']), (t[3], r['previous']), (t[4], t[0])):
            p.emit('div', dst, src, t[1])
        p.emit('sub', t[2], t[2], t[3])
        p.emit('sub', t[4], t[4], t[3])
        p.emit('add', t[5], t[2], t[4])
        p.emit('flt', a=t[5], b=zero, immediate=prefix+'curvature_ok')
        p.emit('fault', immediate=10)
        p.label(prefix+'curvature_ok')
        p.emit('sub', t[2], t[2], t[4])
        p.emit('mul', t[2], half, t[2])
        p.emit('div', t[2], t[2], t[5])
        p.emit('fge', a=t[2], b=nhalf, immediate=prefix+'min_clip')
        p.emit('mov', t[2], nhalf)
        p.label(prefix+'min_clip')
        p.emit('fge', a=half, b=t[2], immediate=prefix+'max_clip')
        p.emit('mov', t[2], half)
        p.label(prefix+'max_clip')
        p.emit('iadd', t[6], r['sample_index'], immediate=0xffffffff)
        p.emit('u2f', t[7], t[6])
        p.emit('add', t[7], t[7], t[2])
        p.emit('jz', a=r['last_valid'], immediate=prefix+'accept')
        p.emit('sub', t[8], t[7], r['last_peak_position'])
        p.emit('flt', a=t[8], b=low, immediate=prefix+'finish')
        p.emit('fge', a=high, b=t[8], immediate=prefix+'append')
        for name in ('ibi_count', 'bpm', 'bpm_valid'):
            p.emit('imm', r[name])
        for j in range(5):
            p.emit('imm', r['ibi0']+j)
        p.emit('jump', immediate=prefix+'accept')
        p.label(prefix+'append')
        for n in range(5):
            p.emit('ieq', a=r['ibi_count'], b=p.constant(n, integer=True), immediate=prefix+f'append{n}')
        for j in range(4):
            p.emit('mov', r['ibi0']+j, r['ibi0']+j+1)
        p.emit('mov', r['ibi4'], t[8])
        p.emit('jump', immediate=prefix+'median')
        for n in range(5):
            p.label(prefix+f'append{n}')
            p.emit('mov', r['ibi0']+n, t[8])
            p.emit('iadd', r['ibi_count'], r['ibi_count'], immediate=1)
            p.emit('jump', immediate=prefix+'median')
        p.label(prefix+'median')
        for n in range(1, 6):
            p.emit('ieq', a=r['ibi_count'], b=p.constant(n, integer=True), immediate=prefix+f'sort{n}')
        p.emit('fault', immediate=11)
        for n in range(1, 6):
            p.label(prefix+f'sort{n}')
            for j in range(n):
                p.emit('mov', t[9]+j, r['ibi0']+j)
            for j in range(n-1):
                for k in range(n-1-j):
                    label=prefix+f'sort{n}_{j}_{k}'
                    p.emit('fge', a=t[10]+k, b=t[9]+k, immediate=label)
                    p.emit('mov', t[14], t[9]+k)
                    p.emit('mov', t[9]+k, t[10]+k)
                    p.emit('mov', t[10]+k, t[14])
                    p.label(label)
            if n % 2:
                p.emit('mov', t[14], t[9]+n//2)
            else:
                p.emit('add', t[14], t[9]+n//2-1, t[9]+n//2)
                p.emit('div', t[14], t[14], two)
            p.emit('div', r['bpm'], bpm_numerator, t[14])
            p.emit('imm', r['bpm_valid'], immediate=1)
            p.emit('jump', immediate=prefix+'accept')
        p.label(prefix+'accept')
        p.emit('imm', r['peak'], immediate=1)
        p.emit('iadd', r['accepted_peak_count'], r['accepted_peak_count'], immediate=1)
        p.emit('mov', r['last_peak_index'], t[6])
        p.emit('mov', r['last_peak_position'], t[7])
        p.emit('imm', r['last_valid'], immediate=1)
        p.label(prefix+'finish')
        p.emit('mov', r['previous_previous'], r['previous'])
        p.emit('mov', r['previous'], t[0])
        p.emit('mov', r['previous_previous_trusted'], r['previous_trusted'])
        p.emit('jnz', a=3, immediate=prefix+'trust_copy')
        p.emit('imm', r['previous_previous_trusted'])
        p.label(prefix+'trust_copy')
        p.emit('mov', r['previous_trusted'], 3)
        p.emit('iadd', r['sample_index'], r['sample_index'], immediate=1)
        p.emit('imm', base+24, immediate=1)  # interval-key cache initialized
    p.emit('mov', 14, 10)
    p.emit('mov', 10, 12)
    p.emit('ieq', a=11, b=i2, immediate='bank_done')
    p.emit('iadd', 11, 11, immediate=1)
    p.label('bank_done')
    p.emit('done')
    code = p.finish()
    return dict(code=code, constants=p.constants, entries={k:p.labels[k] for k in ('prep','bank')},
                instructions=len(code), layout=LAYOUT, globals=GLOBALS)


def export_program(output, config, sections):
    output=Path(output)
    result=compile_program(config, sections)
    for name, words, length in (('program',result['code'],4096),('constants',result['constants'],64)):
        with (output/f'small_heart_{name}.mem').open('x', encoding='ascii') as stream:
            stream.write(''.join(f'{x:016x}\n' for x in words+[0]*(length-len(words))))
    return result
