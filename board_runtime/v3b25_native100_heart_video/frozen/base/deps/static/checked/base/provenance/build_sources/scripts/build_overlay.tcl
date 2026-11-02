# 真正整板实现；bit阶段只读取已核对的同一个路由checkpoint。
set stage arguments
if {[catch {
    if {[llength $argv]!=2} {error "expected session and route/bit"}
    set session [file normalize [lindex $argv 0]]
    set mode [lindex $argv 1]
    set reports "$session/reports"
    if {$mode eq "bit"} {
        set stage bitstream
        open_checkpoint "$reports/routed.dcp"
        write_bitstream "$session/heart_v3a.bit"
        puts "V3A_OVERLAY_BIT_WRITTEN"
    } elseif {$mode eq "route"} {
        set_param general.maxThreads 4
        set_param board.repoPaths [list "$session/board_repo"]
        open_project "$session/heart_v3a/heart_v3a.xpr"
        set_property ip_repo_paths [list "$session/ip_repo"] [current_project]
        update_ip_catalog
        file mkdir $reports
        set_property STEPS.SYNTH_DESIGN.ARGS.RETIMING false [get_runs synth_1]
        set_property strategy Performance_Explore [get_runs impl_1]
        set stage synthesis
        launch_runs synth_1 -jobs 4
        wait_on_run synth_1
        if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {error "synth run not complete"}
        open_run synth_1
        report_utilization -hierarchical -file "$reports/synth_utilization.rpt"
        close_design
        set stage implementation
        launch_runs impl_1 -to_step route_design -jobs 4
        wait_on_run impl_1
        if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {error "implementation run not complete"}
        open_run impl_1
        set stage physical_optimization
        phys_opt_design -directive ExploreWithHoldFix
        route_design -preserve
        set stage reports
        report_timing_summary -delay_type min_max -report_unconstrained -file "$reports/timing_summary.rpt"
        check_timing -verbose -file "$reports/check_timing.rpt"
        report_clocks -file "$reports/clock.rpt"
        report_drc -file "$reports/drc.rpt"
        report_utilization -file "$reports/utilization.rpt"
        report_utilization -hierarchical -file "$reports/hierarchical_utilization.rpt"
        foreach {label path} {nlms design_1_i/nlms_axi_0 fifo design_1_i/axi_fifo_mm_s_0 iic design_1_i/axi_iic_0} {
            set cells [get_cells -quiet $path]
            if {[llength $cells]!=1} {error "missing integrated hierarchy $path"}
            report_utilization -cells $cells -file "$reports/${label}_utilization.rpt"
        }
        set setup [get_timing_paths -delay_type max -max_paths 1]
        set hold [get_timing_paths -delay_type min -max_paths 1]
        if {[llength $setup]!=1 || [llength $hold]!=1} {error "missing full setup/hold paths"}
        set wns [get_property SLACK $setup]
        set whs [get_property SLACK $hold]
        set core_clock [get_clocks -of_objects [get_pins design_1_i/nlms_axi_0/s_axi_aclk]]
        if {[llength $core_clock]!=1} {error "missing unique NLMS clock"}
        set period [get_property PERIOD $core_clock]
        set errors [llength [get_drc_violations -filter {SEVERITY == Error}]]
        set check [open "$reports/check_timing.rpt" r];set contents [read $check];close $check
        if {![regexp {checking unconstrained_internal_endpoints \(([0-9]+)\)} $contents ignored unconstrained]} {error "missing internal timing check"}
        set out [open "$reports/timing_metrics.json" {WRONLY CREAT EXCL}]
        puts $out [format {{"wns_ns":%s,"whs_ns":%s,"clock_period_ns":%s,"drc_errors":%d,"unconstrained_internal_endpoints":%d}} $wns $whs $period $errors $unconstrained]
        close $out
        set out [open "$reports/io_pins.json" {WRONLY CREAT EXCL}]
        set scl [get_ports -quiet i2c_scl_io];set sda [get_ports -quiet i2c_sda_io]
        if {[llength $scl]!=1 || [llength $sda]!=1} {error "missing original IIC ports"}
        if {[get_property IOSTANDARD $scl] ne "LVCMOS33" || [get_property IOSTANDARD $sda] ne "LVCMOS33"} {error "IIC voltage changed"}
        puts $out [format {{"i2c_scl_io":"%s","i2c_sda_io":"%s"}} [get_property PACKAGE_PIN $scl] [get_property PACKAGE_PIN $sda]]
        close $out
        set out [open "$reports/run_status.json" {WRONLY CREAT EXCL}]
        puts $out [format {{"tool_version":"%s","synth_status":"%s","impl_status":"%s","core_clock":"%s"}} [version -short] [get_property STATUS [get_runs synth_1]] [get_property STATUS [get_runs impl_1]] $core_clock]
        close $out
        write_checkpoint "$reports/routed.dcp"
        puts "V3A_OVERLAY_ROUTE_REPORTED"
        close_project
    } else {error "unknown build mode"}
} message options]} {
    puts stderr "ERROR: V3A_OVERLAY stage=$stage: $message"
    puts stderr [dict get $options -errorinfo]
    exit 1
}
exit 0
