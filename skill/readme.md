> Install with `python3 -B prepare_delivery.py skills --output ../trusted_heart_skills` from the repository root. The generated `skill/skills/` restores original `SKILL.md` and example names. Lowercase `skill.md` files here are storage/review copies; all 66 Skill files retain their exact original bytes.

# Eight PYNQ engineering Skills

All eight directories under `skills/` include their original `SKILL.md`, references, tools and MIT license. Four framework skills also include independent unit tests and synthetic examples. Source contents are preserved; Git checkouts may normalize line endings. This export did not run the tests.

| Skill | Review/use scope |
|---|---|
| [pynq-overlay-portability](skills/pynq-overlay-portability/skill.md) | HWH/profile compatibility and driver-binding metadata |
| [pynq-dma-lifecycle](skills/pynq-dma-lifecycle/skill.md) | Offline DMA ownership, cache and release event audit |
| [pynq-notebook-delivery](skills/pynq-notebook-delivery/skill.md) | Source identity, seal/verify and reviewed pure-software spawn |
| [pynq-ps-pl-profiler](skills/pynq-ps-pl-profiler/skill.md) | Explicit-clock phase timing, ABBA and numerical comparison |
| [pynq-result-audit](skills/pynq-result-audit/skill.md) | Read-only ZIP/CSV/JSON result and cleanup evidence |
| [pynq-board-session](skills/pynq-board-session/skill.md) | Package identity, single ownership and deployment evidence |
| [ps-pl-performance](skills/ps-pl-performance/skill.md) | Ordinary ABBA CSV and contiguous-block latency review |
| [fpga-kernel-verification](skills/fpga-kernel-verification/skill.md) | Numerical/RTL/interface/implementation/board evidence levels |

Read the chosen Skill before use; it defines inputs, limitations and examples. Skills are not automatically installed. Copy this directory to a fresh scratch location before running checks so the published snapshot remains unchanged. For each framework skill, run `python -B -m unittest discover -s tests -v` from its own directory when software test execution is authorized. The unchanged `legacy_cli_check.py` in this directory generates synthetic fixtures and checks the original three CLIs; it does not access hardware or network.

`historical_validation.json` records the same **31+37+37+29=134 unit cases** in original and isolated extraction checks; repeated runs are not additional unique cases. `historical_cli_validation.json` records **38 shared synthetic CLI assertions**, a separate category. The FPGA workflow skill has no independent RTL unit-test count. These historical results are not newly executed export tests and do not prove ARM, second-board or medical accuracy performance.

Local source manifests, original ZIP copies, absolute machine paths, generated test logs and private provenance have been excluded. Individual Skill source/docs/examples/tests remain complete. No board operation is authorized by reading or publishing a Skill.

## Project entry

The project example is `../board_runtime/runtime/ContinuousDemo25.ipynb`. First run the root `prepare_delivery.py runtime` command and use the generated `board_runtime/` directory, where original names are restored. See the root README and `../board/README.md` for versions, four-cell operation and normal stop. The eight Skill source directories remain unchanged. Historical Skill tests and the superseded `public_live` wrapper tests are separate from the saved 33.19-second board run and do not establish a new hardware acceptance.
