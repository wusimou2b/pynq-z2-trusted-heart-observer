# Published names and deployment validation

The 2026-11-03 revision separates public storage names from generated deployment
names. Repository and source-archive paths use lowercase ASCII letters, digits,
underscores, hyphens and extension separators. No Chinese or whitespace names
are required in the uploaded tree. Original names remain in the mapping JSON
contents because they are needed by the frozen runtime and Skills loaders.

## Reproduce the file checks

Run from a pristine source checkout with Python 3.10 or newer:

```sh
python3 -B verify_public_source.py
python3 -B prepare_delivery.py runtime --check-only
python3 -B prepare_delivery.py runtime --output ../trusted_heart_demo
python3 -B ../trusted_heart_demo/board_runtime/verify_portable.py
python3 -B prepare_delivery.py skills --output ../trusted_heart_skills
python3 -B -m unittest discover -s tests -v
```

Both output directories must be new and outside the checkout. The preparation
step verifies inputs before creating the destination, then checks copied bytes.
It refuses corrupt or missing sources, path escapes, duplicate/case-colliding
destinations, file/directory collisions and existing output directories.
Failed attempts are retained for inspection; they are not marked complete.

## Actual local evidence

- 15 preparation regression tests passed, including failure paths.
- All 958 runtime files were restored and compared byte-for-byte against the
  published baseline commit `4e2383892a1bd5e13476e6ab46243dffc97c800a`.
- The original `verify_portable.py` then exited 0, reporting `complete=true`,
  `verified_members=957`, and `hardware_accessed=false`. The additional file is
  the portable manifest itself.
- Preparation and the original verifier also passed under Ubuntu/WSL with
  Python 3.12.3, restoring into a case-sensitive Linux temporary filesystem.
  This is an independent filesystem/path check, not an ARM or board test.
- Runtime manifest SHA256 remains
  `4c92d15dae3410510c4f5e995d92d1e2a00d1c2b242623fd72ba837330311f02`.
- ARM library SHA256 remains
  `4dc17698315564f4d2ac50b5e3d1607fecfe12f2520dafa9f4aaa40ff4e50c78`.
- All 66 files of the eight Skills were restored with original bytes and names,
  including loader-required `SKILL.md` files.
- The four Skills with independent test suites were re-run from restored copies:
  37 DMA + 37 delivery + 31 overlay + 29 profiler = 134 passing tests.
- The eleven retained runtime ZIP files contain compliant member names and
  retain their original bytes.

No board access, PL download, ARM native execution, new acquisition or new
medical/performance acceptance was performed by these checks. This preparation
is a one-time offline file operation and adds no code to the processing loop.
Build validation is separate and described in `../build/readme.md`.

The normalized runtime notebooks are review/storage files. Run only the restored
deployment, as described in the root readme. The preparation tool does not install
system packages or replace the documented ARM/PYNQ environment requirements.
