# One full-design synthesis/route, preserve reports even when timing fails.
set stage arguments
if {[catch {
    set session [file normalize [lindex $argv 0]]
    set_param general.maxThreads 2
    set_param board.repoPaths [list "$session/board_repo"]
    open_project "$session/project/heart_v3b25.xpr"
    set_property ip_repo_paths [list "$session/ip_repo"] [current_project]
    update_ip_catalog
    file mkdir "$session/reports"
    set reports "$session/reports"
    set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY none [get_runs synth_1]
    set_property strategy Performance_Explore [get_runs impl_1]
    set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED false [get_runs impl_1]
    set stage synthesis
    puts "V3B25_WHOLE_STAGE $stage"
    launch_runs synth_1 -jobs 2
    wait_on_run synth_1
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "Synthesis did not complete"}
    open_run synth_1
    report_utilization -hierarchical -file "$reports/synth_utilization.rpt"
    close_design
    set stage implementation
    puts "V3B25_WHOLE_STAGE $stage"
    launch_runs impl_1 -to_step route_design -jobs 2
    wait_on_run impl_1
    if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "Implementation did not complete"}
    open_run impl_1
    set stage physical_optimization
    puts "V3B25_WHOLE_STAGE $stage"
    phys_opt_design -hold_fix
    route_design -preserve
    set main [get_cells -quiet design_1_i/heart_main_0]
    if {[llength $main]!=1 || [llength [get_cells -quiet design_1_i/nlms_axi_0]] || [llength [get_cells -quiet design_1_i/heart_candidates_0]]} {error "continuous main topology changed"}
    set fp [get_cells -hier -filter {NAME =~ design_1_i/heart_main_0/* && REF_NAME =~ *history100_fp64*}]
    set nlms [get_cells -hier -filter {NAME =~ design_1_i/heart_main_0/* && REF_NAME =~ *nlms_core_runtime_3x4*}]
    if {[llength $fp]!=1 || [llength $nlms]!=1} {error "exactly one actual FP64/NLMS required"}
    set main_clock [get_clocks -of_objects [get_pins design_1_i/heart_main_0/aclk]]
    if {[llength $main_clock]!=1 || [get_property PERIOD $main_clock]!=10.0} {error "actual main100MHz clock differs"}
    if {$main_clock ne [get_clocks -of_objects [get_pins design_1_i/vision_0/aclk]]} {error "main/video AXI clock domain differs"}
    if {[get_nets -of_objects [get_pins design_1_i/heart_main_0/aresetn]] ne [get_nets -of_objects [get_pins design_1_i/vision_0/aresetn]]} {error "main/video reset domain differs"}
    set boxes [get_cells -hier -filter {IS_BLACKBOX == 1}]
    if {[llength $boxes]} {error "unresolved joint blackbox"}
    set core_file [open "$reports/main-core.json" {WRONLY CREAT EXCL}]
    puts $core_file {{"single_fp64":true,"single_nlms":true,"main_clock_hz":100000000,"same_video_reset":true,"old_compute_endpoints_removed":true,"blackboxes":0}}
    close $core_file
    set stage reporting
    puts "V3B25_WHOLE_STAGE $stage"
    report_utilization -file "$reports/utilization.rpt"
    report_utilization -hierarchical -file "$reports/hierarchical_utilization.rpt"
    foreach name {heart_main_0 vision_0 vision_packet vision_dma display_dma hdmi_vdma hdmi_out} {
        set cell [get_cells -quiet design_1_i/$name]
        if {[llength $cell]!=1} {error "Missing integrated module $name"}
        report_utilization -cells $cell -file "$reports/${name}_utilization.rpt"
    }
    report_timing_summary -delay_type min_max -report_unconstrained -file "$reports/timing_summary.rpt"
    report_timing -delay_type max -max_paths 15 -file "$reports/worst_setup.rpt"
    report_timing -delay_type min -max_paths 15 -file "$reports/worst_hold.rpt"
    check_timing -verbose -file "$reports/check_timing.rpt"
    report_clocks -file "$reports/clocks.rpt"
    report_clock_interaction -file "$reports/clock_interaction.rpt"
    report_cdc -details -file "$reports/cdc.rpt"
    report_drc -file "$reports/drc.rpt"
    report_exceptions -file "$reports/exceptions.rpt"
    report_io -file "$reports/io.rpt"
    set out [open "$reports/pins.tsv" {WRONLY CREAT EXCL}]
    foreach {port pin standard} {
       i2c_scl_io P15 LVCMOS33 i2c_sda_io P16 LVCMOS33
       hdmi_out_clk_n L17 TMDS_33 hdmi_out_clk_p L16 TMDS_33
       {hdmi_out_data_n[0]} K18 TMDS_33 {hdmi_out_data_p[0]} K17 TMDS_33
       {hdmi_out_data_n[1]} J19 TMDS_33 {hdmi_out_data_p[1]} K19 TMDS_33
       {hdmi_out_data_n[2]} H18 TMDS_33 {hdmi_out_data_p[2]} J18 TMDS_33
       {hdmi_out_hpd[0]} R19 LVCMOS33
    } {
        set object [get_ports -quiet $port]
        if {[llength $object]!=1 || [get_property PACKAGE_PIN $object] ne $pin || [get_property IOSTANDARD $object] ne $standard} {error "Wrong physical pin or standard: $port"}
        puts $out "$port\t[get_property PACKAGE_PIN $object]\t[get_property IOSTANDARD $object]"
    }
    close $out
    set setup [get_timing_paths -delay_type max -max_paths 1]
    set hold [get_timing_paths -delay_type min -max_paths 1]
    if {[llength $setup]!=1 || [llength $hold]!=1} {error "Missing actual constrained timing paths"}
    set axi_clock [get_clocks -of_objects [get_pins design_1_i/vision_0/aclk]]
    if {[llength $axi_clock]!=1} {error "Missing unique AXI/vision clock"}
    set pixel_clock [get_clocks -of_objects [get_pins design_1_i/hdmi_out/frontend/rgb2dvi/U0/PixelClk]]
    set serial_clock [get_clocks -of_objects [get_pins design_1_i/hdmi_out/frontend/rgb2dvi/U0/SerialClk]]
    if {[llength $pixel_clock]!=1 || [llength $serial_clock]!=1} {error "Missing/duplicate physical HDMI clocks"}
    set pixel_period [get_property PERIOD $pixel_clock]
    set serial_period [get_property PERIOD $serial_clock]
    if {abs($pixel_period - 5.0*$serial_period)>0.001} {error "Physical HDMI clock ratio is not 5:1"}
    set out [open "$reports/hdmi-clock-model.tsv" {WRONLY CREAT EXCL}]
    puts $out "pixel\t$pixel_clock\t$pixel_period"
    puts $out "serial\t$serial_clock\t$serial_period"
    puts $out "scope\tMMCM power-on static model; runtime mode not board-measured"
    close $out
    set drc_errors [llength [get_drc_violations -quiet -filter {SEVERITY == Error}]]
    set drc_critical [llength [get_drc_violations -quiet -filter {SEVERITY == "Critical Warning"}]]
    set out [open "$reports/raw-metrics.json" {WRONLY CREAT EXCL}]
    puts $out [format {{"wns_ns":%s,"whs_ns":%s,"axi_period_ns":%s,"drc_errors":%d,"drc_critical":%d,"route_status":"%s","all_pins_verified":true,"external_interface_timing_reviewed":false}} [get_property SLACK $setup] [get_property SLACK $hold] [get_property PERIOD $axi_clock] $drc_errors $drc_critical [get_property STATUS [get_runs impl_1]]]
    close $out
    write_checkpoint "$session/routed.dcp"
    puts "MAIN_HEART_JOINT_ROUTE_REPORTED"
    close_project
} message options]} {
    puts stderr "ERROR: V3B25_WHOLE stage=$stage: $message"
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
