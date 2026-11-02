# Simulation and software test evidence

`round-equivalence/inputs/` contains the four non-physiological RTL inputs for an exhaustive signed16 exponent/round-carry predicate check. `reference/` preserves the original expression and transformation source. `case.json` and `evidence/equivalence.json` have historical machine paths reduced to basenames. The historical result reports 131072 checked conditions. It was not rerun during export.

For review, the case records the original xvlog compile order, top module and required pass marker. Run HDL tools only in a separately authorized fresh output directory. The original reference transformation imports historical project helpers that are not included as a complete build API.

`hardware_validation_summary.json` records historical test counts and incomplete integration flags. This `sim/` selection is a historical simulation subset. The separately preserved `../board_runtime/` retains its user-authorized numerical measurements, derived qualification inputs and eight-point hardware-free preflight data; do not infer that those dependencies are absent from the runtime. Eight-Skill standalone tools/tests and synthetic assets are under `../skill/`; their historical 134 unit cases and 38 shared CLI assertions are different evidence categories. No engineering test was executed as part of this export.
