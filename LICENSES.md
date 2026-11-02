# Component licenses

The root MIT license applies to original project code within its stated scope. It does not replace third-party terms or attribution.

- `licenses/native/`: CPython 3.10.4, NumPy 1.21.5, GCC 11.2 GPL and GCC Runtime Library Exception, plus the project source notice preserved from the earlier native distribution.
- `licenses/hardware/`: preserved Digilent RGB2DVI BSD, Xilinx MMCM, PocketFFT and project notices, with the original AMD source links.
- `src/licenses/`, `src/hls/LICENSE` and `src/third_party/`: corresponding arithmetic, PocketFFT and PYNQ/HLS sources and notices.
- `skill/skills/`: each Skill retains its own license.

The 958 files in `board_runtime/` retain their exact verified bytes, including the corresponding C/assembly/Python sources and original ARM binaries. The surrounding license files apply to the relevant components without changing the runtime identity chain. No native binary was rebuilt for publication.

The public tree does not redistribute entire AMD generated-IP repositories or board-definition collections with unconfirmed distribution terms. The required external tool/IP/board prerequisites remain documented in `build/external_dependencies.md`.
