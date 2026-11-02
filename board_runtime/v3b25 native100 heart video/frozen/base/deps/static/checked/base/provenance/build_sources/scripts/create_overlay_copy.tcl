# 只操作新目录里的BD，原工程从不open_project。
set session [file normalize [lindex $argv 0]]
set staged_bd [file normalize [lindex $argv 1]]
set_param board.repoPaths [list "$session/board_repo"]
create_project heart_v3a "$session/heart_v3a" -part xc7z020clg400-1
set bd "$session/heart_v3a/heart_v3a.srcs/sources_1/bd/design_1/design_1.bd"
file mkdir [file dirname $bd]
if {[file exists $bd]} {error "New BD path unexpectedly occupied"}
file copy $staged_bd $bd
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property ip_repo_paths [list "$session/ip_repo"] [current_project]
update_ip_catalog
add_files $bd
open_bd_design $bd
foreach name {processing_system7_0 ps7_0_axi_periph axi_fifo_mm_s_0 axi_iic_0 rst_ps7_0_100M} {
    if {[llength [get_bd_cells -quiet $name]]!=1} {error "Missing original cell $name"}
}
if {[get_property CONFIG.NUM_MI [get_bd_cells ps7_0_axi_periph]]!=2} {error "Unexpected original AXI count"}
set_property CONFIG.NUM_MI 3 [get_bd_cells ps7_0_axi_periph]
create_bd_cell -type ip -vlnv heart.local:signal:nlms_axi_lite:1.0 nlms_axi_0
foreach pin {ps7_0_axi_periph/M02_AXI nlms_axi_0/S_AXI} {
    if {[llength [get_bd_intf_pins -quiet $pin]]!=1} {error "Missing interface $pin"}
}
foreach pin {processing_system7_0/FCLK_CLK0 nlms_axi_0/s_axi_aclk ps7_0_axi_periph/M02_ACLK rst_ps7_0_100M/peripheral_aresetn nlms_axi_0/s_axi_aresetn ps7_0_axi_periph/M02_ARESETN} {
    if {[llength [get_bd_pins -quiet $pin]]!=1} {error "Missing pin $pin"}
}
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M02_AXI] [get_bd_intf_pins nlms_axi_0/S_AXI]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins nlms_axi_0/s_axi_aclk] [get_bd_pins ps7_0_axi_periph/M02_ACLK]
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins nlms_axi_0/s_axi_aresetn] [get_bd_pins ps7_0_axi_periph/M02_ARESETN]
assign_bd_address -offset 0x43C10000 -range 64K -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs nlms_axi_0/S_AXI/Reg]
validate_bd_design
save_bd_design
set out [open "$session/validation.tsv" w]
puts $out "bd\t$bd"
foreach {master slave} {M00 axi_fifo_mm_s_0/S_AXI M01 axi_iic_0/S_AXI M02 nlms_axi_0/S_AXI} {
    set net [get_bd_intf_nets -of_objects [get_bd_intf_pins ps7_0_axi_periph/${master}_AXI]]
    set peers [get_bd_intf_pins -of_objects $net]
    if {[lsearch -exact $peers [get_bd_intf_pins $slave]]<0} {error "Incorrect $master destination"}
    puts $out "$master\t$slave"
}
set clknet [get_bd_nets -of_objects [get_bd_pins processing_system7_0/FCLK_CLK0]]
foreach pin {nlms_axi_0/s_axi_aclk ps7_0_axi_periph/M02_ACLK} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $clknet} {error "Clock association mismatch"}
}
set rstnet [get_bd_nets -of_objects [get_bd_pins rst_ps7_0_100M/peripheral_aresetn]]
foreach pin {nlms_axi_0/s_axi_aresetn ps7_0_axi_periph/M02_ARESETN} {
    if {[get_bd_nets -of_objects [get_bd_pins $pin]] ne $rstnet} {error "Reset association mismatch"}
}
puts $out "clock_hz\t[get_property CONFIG.FREQ_HZ [get_bd_pins nlms_axi_0/s_axi_aclk]]"
puts $out "reset\trst_ps7_0_100M/peripheral_aresetn"
puts $out "ports\t[join [lsort [get_bd_ports]] ,]"
close $out
generate_target all [get_files $bd]
add_files [make_wrapper -files [get_files $bd] -top]
set_property top design_1_wrapper [current_fileset]
update_compile_order -fileset sources_1
# 调用者对本次真实日志执行Error／Critical Warning门。
puts "V3A_OVERLAY_COPY_PASS"
close_project
