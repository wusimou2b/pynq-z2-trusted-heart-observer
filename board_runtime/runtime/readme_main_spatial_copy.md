# Reference display-reader port

Original418 files, PL bit/HWH, C library, heart path,4x3 motion, MPU fusion, HDMI video/text and browser four curves are unchanged. Only the display reader copies bounded bytes under the lock and decodes after releasing it.

25/25Hz +5fps,700-point warmup,60s READY,180s startup,50ms mailbox lock, 20ms whole hardware transaction and1s step/exit/freshness remain unchanged. GC and queue capacity are unchanged. No PyDLL substitution.

Use MainSpatialCopy25.ipynb in this new directory. The first cell checks the original PS short exit without hardware. The second prepares the original browser/normal-stop button. Wait for green, then manually confirm the third cell. Stop normally around60s on the first trial. Failure is preserved without retry; do not interrupt the kernel instead of cleanup.

The reference completed127 points in5s but forced PS termination. This port is not evidence of repaired33ms latency, natural exit, or full acceptance. No board execution is performed by the local builder.
