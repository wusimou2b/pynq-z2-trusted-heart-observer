# Generate a file only, from the reviewed original routed checkpoint.
# No project/board connection, reroute, MMCM change, new constraint or retry.
proc one {objects label} {
    if {[llength $objects] != 1} {error "Expected one $label: $objects"}
    return [lindex $objects 0]
}
if {[catch {
    if {[llength $argv] != 2} {error "Expected original DCP and fresh output directory"}
    set checkpoint [file normalize [lindex $argv 0]]
    set session [file normalize [lindex $argv 1]]
    set_param general.maxThreads 4
    open_checkpoint $checkpoint
    set part [get_property PART [current_design]]
    if {$part ne "xc7z020clg400-1"} {error "Wrong target part: $part"}
    set setup [one [get_timing_paths -delay_type max -max_paths 1] setup]
    set hold [one [get_timing_paths -delay_type min -max_paths 1] hold]
    set wns [get_property SLACK $setup]
    set whs [get_property SLACK $hold]
    set axi [get_property PERIOD [one [get_clocks -of_objects [get_pins design_1_i/vision_0/aclk]] AXI]]
    set pixel [get_property PERIOD [one [get_clocks -of_objects [get_pins design_1_i/hdmi_out/frontend/rgb2dvi/U0/PixelClk]] pixel]]
    set serial [get_property PERIOD [one [get_clocks -of_objects [get_pins design_1_i/hdmi_out/frontend/rgb2dvi/U0/SerialClk]] serial]]
    if {$wns < 0 || $whs < 0 || $axi != 10.0 || $pixel != 10.0 || $serial != 2.0} {error "Not the reviewed original static clock/timing model"}
    report_route_status -file "$session/route_status.rpt"
    report_drc -file "$session/write_drc.rpt"
    set errors [llength [get_drc_violations -quiet -filter {SEVERITY == Error}]]
    set critical [llength [get_drc_violations -quiet -filter {SEVERITY == "Critical Warning"}]]
    if {$errors != 0 || $critical != 0} {error "Fresh bitstream DRC gate failed"}
    set out [open "$session/bit-write-readback.json" {WRONLY CREAT EXCL}]
    puts $out [format {{"part":"%s","wns_ns":%s,"whs_ns":%s,"axi_ns":%s,"pixel_ns":%s,"serial_ns":%s,"drc_errors":%d,"drc_critical":%d}} $part $wns $whs $axi $pixel $serial $errors $critical]
    close $out
    if {[file exists "$session/artifacts/heart_v3b25.bit"]} {error "Output bit already exists"}
    write_bitstream "$session/artifacts/heart_v3b25.bit"
    puts "V3B25_MATCHED_BITSTREAM_WRITTEN"
    close_design
} message options]} {
    puts stderr "ERROR: V3B25_BITSTREAM: $message"
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
