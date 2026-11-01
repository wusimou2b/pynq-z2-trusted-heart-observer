# Source-layout handover

The original Python package layout is preserved for the public LIVE implementation. Original guards and historical entry functions remain legacy source, not the new public verification authority. Historical notebooks and saved outputs were not exported as entry points. No Python source was edited by this exporter.

The exact compact_hardware pair is supplied; other historical same-basename overlays are omitted. Authored native readback/scheduling/sample libraries and their C/assembly inputs are retained where original loaders expect them. The exact statistics extension resides in ../native_source/native-build/. Fixed ARM SOS coefficients are in assets/arm_sos.json, extracted without recorded runs from the original comparison JSON.

Private recorded CSVs, private input/result archives and derived recorded cases/vectors are not LIVE inputs and are not supplied. A new public guard, explicit source/asset manifest and clean notebook entry are being implemented separately; this initial source-layout handover is not a qualified runnable release. No import, compile, load or board operation has occurred.
