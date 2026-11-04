> This published variant excludes all posters; the following is a historical publication note.

# Submission delivery revision — 2026-11-03

This revision addresses three publication defects without changing the frozen
application's processing, guards, hardware files or recorded evidence.

1. **Version identity.** The new `v2026.11.03` tag points to this revision, so its
   automatic GitHub source archives and explicitly attached source packages
   describe the same file tree. The old `public-live` tag and assets remain
   available as historical material; they are not moved or overwritten.
2. **Published names.** All project paths use lowercase ASCII names. The
   `prepare_delivery.py` tool restores original application/Skill filenames in a
   new external deployment directory, verifying every copied byte. This avoids
   changing 958 runtime files or weakening nested manifest checks. It is not a
   processing-loop wrapper and adds no per-sample work.
3. **Build inputs.** `build/inputs/physical-inputs.json` and `.zip` now provide a
   verified source-input contract, pinned external dependency retrieval, local
   HLS generation and the original Vivado implementation checks. This source
   contract differs explicitly from the historical full archive that contained
   tool-generated files. See `build/readme.md` and `build/validation.json` for the
   actual stages completed and their limits.

Start with `readme.md`; do not open a storage-layout runtime notebook directly.
Independent Skills installation also uses the preparation tool to restore the
loader-required `SKILL.md` names.

The video and anonymous report/poster/photo bytes are retained from their
verified prior publication, with copies provided on the new Release. The anonymous
materials ZIP only normalizes the readme/checksum filenames and refreshes its
internal checksum list; its documents and photos are unchanged. Signatures,
authorization paperwork and named participant materials are not included.

Rebuilt hardware artifacts, if produced, are separate validation outputs. They
do not replace the qualified runtime bit/HWH, and no new board run, SD-image
reproduction, medical accuracy or strict-real-time acceptance is implied.
