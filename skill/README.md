# Eight PYNQ engineering Skills

All eight directories under `skills/` include their original `SKILL.md`, references, tools and MIT license. Four framework skills also include independent unit tests and synthetic examples. Files are copied byte-for-byte; this export did not run the tests.

| Skill | Review/use scope |
|---|---|
| [pynq-overlay-portability](skills/pynq-overlay-portability/SKILL.md) | HWH/profile compatibility and driver-binding metadata |
| [pynq-dma-lifecycle](skills/pynq-dma-lifecycle/SKILL.md) | Offline DMA ownership, cache and release event audit |
| [pynq-notebook-delivery](skills/pynq-notebook-delivery/SKILL.md) | Source identity, seal/verify and reviewed pure-software spawn |
| [pynq-ps-pl-profiler](skills/pynq-ps-pl-profiler/SKILL.md) | Explicit-clock phase timing, ABBA and numerical comparison |
| [pynq-result-audit](skills/pynq-result-audit/SKILL.md) | Read-only ZIP/CSV/JSON result and cleanup evidence |
| [pynq-board-session](skills/pynq-board-session/SKILL.md) | Package identity, single ownership and deployment evidence |
| [ps-pl-performance](skills/ps-pl-performance/SKILL.md) | Ordinary ABBA CSV and contiguous-block latency review |
| [fpga-kernel-verification](skills/fpga-kernel-verification/SKILL.md) | Numerical/RTL/interface/implementation/board evidence levels |

Read the chosen Skill before use; it defines inputs, limitations and examples. Skills are not automatically installed. Copy this directory to a fresh scratch location before running checks so the published snapshot remains unchanged. For each framework skill, run `python -B -m unittest discover -s tests -v` from its own directory when software test execution is authorized. The unchanged `legacy_cli_check.py` in this directory generates synthetic fixtures and checks the original three CLIs; it does not access hardware or network.

`historical_validation.json` records the same **31+37+37+29=134 unit cases** in original and isolated extraction checks; repeated runs are not additional unique cases. `historical_cli_validation.json` records **38 shared synthetic CLI assertions**, a separate category. The FPGA workflow skill has no independent RTL unit-test count. These historical results are not newly executed export tests and do not prove ARM, second-board or medical accuracy performance.

Local source manifests, original ZIP copies, absolute machine paths, generated test logs and private provenance have been excluded. Individual Skill source/docs/examples/tests remain complete. No board operation is authorized by reading or publishing a Skill.

## Project entry

The project example is `../public_live/PublicLive.ipynb`; its full identity and Notebook source policy are documented in the adjacent deployment README. The eight Skills remain unchanged reusable sources. The new release's81 software cases are separate from the historical134 Skill cases and38 CLI assertions; no hardware validation is implied.
