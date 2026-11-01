# External dependencies and reproduction prerequisites

## Hardware toolchain

Historical implementation: Vivado 2024.1 with Zynq-7000 device support, `xc7z020clg400-1`, PYNQ-Z2. This public snapshot has not been built in a clean directory. Tool installation and AMD catalog IP are external dependencies supplied under their original licenses.

The PYNQ source inputs are pinned to **Xilinx/PYNQ commit `19ed17d4fd4ea71f95a97d30f8ccd0d62b8dbaaa`**. Obtain that exact upstream revision, verify its license and corresponding source paths before preparing the external IP repository. The local audit verified the selected HLS file Git blobs and SHA256; no download or generation took place during public export.

Included under `src/hls/`: `boards/ip/hls/color_convert/{color_convert.cpp,color_convert.hpp,color_convert_test.cpp,script.tcl}` and `boards/ip/hls/pixel_unpack/{pixel_unpack.cpp,pixel_unpack.hpp,pixel_unpack_test.cpp,script.tcl}`, with upstream BSD-3-Clause LICENSE. Use an appropriately licensed HLS tool and review the original scripts to regenerate compatible `xilinx.com:hls:color_convert:1.0` and `xilinx.com:hls:pixel_unpack:1.0` IP. Regeneration equivalence is unverified.

The BD also needs external `axi_dynclk`, `rgb2dvi`, `color_swap`, TMDS interface definitions and PYNQ-Z2 board definitions. These directories are not republished wholesale here. Retrieve the matching pinned upstream files and their licenses; check file-specific restrictions, including the Xilinx-device-only notice in `mmcme2_drp.v`. The exact covering source/license for every board-definition asset is not yet recorded. One original RGB2DVI documentation PDF reference was absent locally; its HDL/XDC references resolved in the static audit.

`build/rebuild.py` is unchanged historical wrapper source and still requires the original complete physical-input ZIP and index. The public authored-input subset is not that original archive. No wrapper claim of complete reconstruction is made. No DCP is a required original input; routed DCP is generated later by the original flow. The Linux/PYNQ application does not require an invented bare-metal ELF or XSA as its deployment entry.

## PS environment and native code

Historical native evidence records ARMv7 little-endian Linux, CPython 3.10.4, SOABI `cpython-310-arm-linux-gnueabihf`, NumPy 1.21.5, GCC 11.2.0. PYNQ, SciPy, OpenCV, Jupyter/IPython and optional plotting/UI packages are required by relevant paths, but a complete image and exact package lock are not provided. The builder pins the compiler executable SHA256; a matching version label alone is insufficient.

The public LIVE distribution now includes the original qualified statistics extension and four actual native helpers, with corresponding C/assembly and component notices under ../public_live/. Their fixed SHA256 identities are verified by the new manifest before loading. No binary was recompiled or modified. The original preparation/source guards remain historical paths; the new public entry uses explicit contained paths and does not require private recorded qualification input. This separation does not turn historical failed flags into a new numerical or board qualification.

Legacy helper imports `ps_core_placement`, `roi_motion_guard`, `roi_motion_runtime` and `run_nlms_rtl` are not closed within this tree. They are historical support paths and must not be assumed to be complete current entry points.

## Mathematical source-generation inputs

`src/reference/main_heart_operators.py` preserves pinned GNU C Library ARM libm arithmetic semantics and historical input locations; the exact pinned ARM library is not supplied. `main_heart_welch.py` pins PocketFFT and still names a historical source location. The included corresponding Python/RTL/ROM and notices are retained, but fully portable source-generator closure has not been verified. Keep the original LGPL/BSD notices; do not treat generated ROMs as a replacement for corresponding source responsibilities.

The runtime dependency and environment findings are documented in `../reproduction/native_dependency.md` and `../reproduction/environment_evidence_lock.md`. Product display/repository naming does not change the original C extension ABI, fixed hash guards or hardware VLNV. Any change to those compatibility identifiers is a separate decision and qualification step.



Current runtime entry: ../public_live/PublicLive.ipynb; deployment requirements and software-only verification scope are in its README and the repository root. Necessary compatibility identifiers are accepted_preserved.
