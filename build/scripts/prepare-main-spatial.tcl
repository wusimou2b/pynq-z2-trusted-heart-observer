set session [file normalize [lindex $argv 0]]
set_param general.maxThreads 4
set_param board.repoPaths [list "$session/board_repo"]
create_project heart_v3b25 "$session/project" -part xc7z020clg400-1
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property ip_repo_paths [list "$session/ip_repo"] [current_project]
update_ip_catalog
add_files [list "$session/rtl/yuyv_bgrx_axis.sv" "$session/rtl/yuyv_bgrx_bd.sv"]
set_property file_type Verilog [get_files "$session/rtl/yuyv_bgrx_bd.sv"]
update_compile_order -fileset sources_1
set bd "$session/project/heart_v3b25.srcs/sources_1/bd/design_1/design_1.bd"
file mkdir [file dirname $bd]
file copy "$session/input/design_1.bd" $bd
add_files $bd
open_bd_design $bd
if {[get_property VLNV [get_bd_cells vision_0]] ne "v3b25.local:vision:vision_axi_lite:1.0" || [get_property CONFIG.NUM_MI [get_bd_cells ps7_0_axi_periph]]!=16} {error "wrong base design"}
if {[get_property VLNV [get_bd_cells heart_main_0]] ne "v3b25.local:signal:main_heart_joint_axi:1.0" || [get_property CONFIG.WATCHDOG_CYCLES [get_bd_cells heart_main_0]]!=2000000} {error "reviewed main core changed"}
delete_bd_objs [get_bd_cells vision_0]
create_bd_cell -type ip -vlnv v3b25.local:vision:vision_spatial_axi_lite:2.0 vision_0
connect_bd_intf_net [get_bd_intf_pins ps7_0_axi_periph/M03_AXI] [get_bd_intf_pins vision_0/S_AXI]
connect_bd_intf_net [get_bd_intf_pins vision_packet/M_AXIS] [get_bd_intf_pins vision_0/S_AXIS]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] [get_bd_pins vision_0/aclk]
connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] [get_bd_pins vision_0/aresetn]
connect_bd_net [get_bd_pins luma_ready/dout] [get_bd_pins vision_0/m_axis_tready]
assign_bd_address -offset 0x43C80000 -range 64K -with_name SEG_spatial_vision \
    -target_address_space [get_bd_addr_spaces processing_system7_0/Data] [get_bd_addr_segs vision_0/S_AXI/Reg]
validate_bd_design
save_bd_design
write_bd_tcl "$session/spatial-design.tcl"
set_property synth_checkpoint_mode None [get_files $bd]
generate_target all [get_files $bd]
set wrapper [make_wrapper -files [get_files $bd] -top]
add_files $wrapper
set_property top design_1_wrapper [current_fileset]
add_files -fileset constrs_1 "$session/pins.xdc"
update_compile_order -fileset sources_1
set handoffs [glob -nocomplain "$session/project/*.gen/sources_1/bd/design_1/hw_handoff/design_1.hwh"]
if {[llength $handoffs]!=1} {error "missing actual spatial HWH"}
file copy [lindex $handoffs 0] "$session/generated.hwh"
puts "MAIN_SPATIAL_PREPARE_PASS"
close_project
