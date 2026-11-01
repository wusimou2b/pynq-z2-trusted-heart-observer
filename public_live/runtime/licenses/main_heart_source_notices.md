# Continuous main-heart operator provenance

The successful original hardware/software release is not modified by this work.
The newly implemented operator RTL and its corresponding source are kept
available together. Generated ROM tables and microcode are not opaque substitutes
for these sources.

## Logarithm and original ARM pow(x,2) order

`main_heart_operators.py`, `main_heart_log10.sv`, and `main_heart_pow2.sv`
preserve the algorithms/tables and individual rounding order of the pinned GNU
C Library ARM libm. Its exact SHA256 is recorded in the Python implementation.
The original ARM library is authoritative for the targeted operation sequence;
the locally installed glibc2.36 source is supporting provenance, not a different
numeric reference. GNU C Library log/pow source notice:

Copyright (C) 2018-2022 Free Software Foundation, Inc.
This file is part of the GNU C Library.

The GNU C Library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version2.1 of the License, or (at your option) any later version.

The GNU C Library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
Lesser General Public License for more details.

The LGPL license text and corresponding modified source must accompany any
release of these derived portions. No binary-only public release is made by this
local verification step.

`e_log10.c` additionally preserves this original notice:

Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.

Developed at SunPro, a Sun Microsystems, Inc. business.
Permission to use, copy, modify, and distribute this
software is freely granted, provided that this notice
is preserved.

## Original pocketfft100 butterflies

`main_heart_welch.py` implements the original radix4/5/5 butterfly arithmetic
from SciPy1.8.0 `scipy/fft/_pocketfft/pocketfft_hdronly.h`. The fixed SSA program
and `main_heart_welch.sv` execute this unchanged operation order. Source SHA256,
official tag and version are pinned in the implementation and verification
evidence. The source download and original LICENSE.md are retained in the
separate evidence directory.

Copyright (C) 2010-2019 Max-Planck-Society
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice, this
  list of conditions and the following disclaimer in the documentation and/or
  other materials provided with the distribution.
* Neither the name of the copyright holder nor the names of its contributors may
  be used to endorse or promote products derived from this software without
  specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
