# A3-R + C-E joint60 candidate

This is an isolated PS policy candidate for the retained 25/25Hz + 5fps main-heart PL/video build.
The 444 baseline members, integrated bit/HWH, Native100, video motion, MPU shadow fusion,
mixed display, queues, GC, 700-point warmup, original startup/step/exit limits remain retained.

Run StatusJoint60AB.ipynb in this directory, in a fresh kernel. The first cell runs the original
hardware-free short exit check, the second prepares the browser display, the third requires
RUN-STATUS-JOINT60AB and performs one manual60-second joint attempt. Do not run another
capture/PL/camera entry concurrently. Connect HDMI OUT/camera before running and hold the finger steady.
Warmup is separate. Original faults may stop early. Do not retry after failure or interrupt cleanup.
Return status60-ab-results.zip and preserve the entire result directory.

A3-R uses the latest real IMU for the latest PPG, and a causal historical IMU read for older batch rows
only when age <=80ms and that physical read has not already supplied another old row.
Each read can be used once for its own latest row and once additionally; this is explicitly reuse,
not extra independent samples. pair_delta_ns=source_read_ns-target_ns; historical age=-pair_delta_ns.

C-E changes the raw gap policy: independent raw/processing supervisors use an observed-record40ms
grid only when actual FIFO pointers/counts, run/config identity, <=500ms host batch interval and
the <=80ms count-vs-host error over2seconds pass. Each supervisor owns <=128 anchors. The original
host time remains in CSV/Slot/display. Freshness continues using the true PPG read_completed_ns.
The record sequence and model grid do not prove the ADC has never lost data. Formal full32-entry
batches are rejected; startup discard32/overflow31 is handled separately with its actual pointer anchor.

The original joint bootstrap/JointBinding creates hardware and the existing source is retained,
including its video arm callback. The actual main_spatial_ps target is wrapped before its capture;
the main SAMPLE protocol and Native100 PS tail are not replaced by an ordinary NLMS worker.
Hardware faults retain their original first cause; later evidence rejection cannot overwrite it.

Canonical config identity is SHA256 of UTF-8 json.dumps(identity,sort_keys=True,
separators=(',',':'),ensure_ascii=False). The identity includes the checked actual sensor readback,
rates, manifest hash, policy versions and integrated bit/HWH hashes. run_epoch is a separate UUID.
The manifest validates449 file byte hashes plus the new Notebook's ordered source identity.
Notebook outputs/execution counts may change; source code/Markdown must not be edited.

Audits are exported after the original resource-retention boundary to continuous-results/a3c/,
and are included by the original stopped-session archive. Native startup/PS errors remain visible;
forced=true with exitcode0 is not a successful natural exit. No full V3B/DDR/accuracy/long-run
acceptance is claimed.80ms pairing/evidence margins in saved data are only8.139/8.529ms, so a new
run can still fail. Thresholds, future-source rejection and no-retry behavior are not relaxed.
