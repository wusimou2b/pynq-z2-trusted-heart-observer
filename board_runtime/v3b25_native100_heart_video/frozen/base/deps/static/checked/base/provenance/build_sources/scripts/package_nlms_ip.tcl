# 新会话内封装AXI邮箱，显式总线／内存映射／时钟／复位，不写原工程。
set session [file normalize [lindex $argv 0]]
set repo "$session/ip_repo/nlms_axi_lite"
if {[file exists "$repo/component.xml"]} {error "IP session already exists"}
create_project ip_package "$session/ip_package" -part xc7z020clg400-1
add_files [glob "$session/snapshot/*.sv"]
set_property top nlms_axi_lite [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $repo -vendor heart.local -library signal -taxonomy /SignalProcessing -import_files -set_current true
set core [ipx::current_core]
set_property name nlms_axi_lite $core
set_property version 1.0 $core
set_property display_name {Triaxial clipped NLMS runtime mailbox} $core
set_property description {Atomic AXI4-Lite mailbox for the 3x4 runtime-beta NLMS core} $core
foreach bus [ipx::get_bus_interfaces -of_objects $core] {
    ipx::remove_bus_interface [get_property NAME $bus] $core
}
foreach memory [ipx::get_memory_maps -of_objects $core] {
    ipx::remove_memory_map [get_property NAME $memory] $core
}
set bus [ipx::add_bus_interface S_AXI $core]
set_property interface_mode slave $bus
set_property bus_type_vlnv xilinx.com:interface:aximm:1.0 $bus
set_property abstraction_type_vlnv xilinx.com:interface:aximm_rtl:1.0 $bus
foreach name {AWADDR AWPROT AWVALID AWREADY WDATA WSTRB WVALID WREADY BRESP BVALID BREADY ARADDR ARPROT ARVALID ARREADY RDATA RRESP RVALID RREADY} {
    set mapping [ipx::add_port_map $name $bus]
    set_property physical_name "s_axi_[string tolower $name]" $mapping
}
foreach {name value} {PROTOCOL AXI4LITE DATA_WIDTH 32 ADDR_WIDTH 16 READ_WRITE_MODE READ_WRITE} {
    set param [ipx::add_bus_parameter $name $bus];set_property value $value $param
}
set memory [ipx::add_memory_map S_AXI $core]
set block [ipx::add_address_block Reg $memory]
set_property range 65536 $block
set_property width 32 $block
set_property usage register $block
set_property slave_memory_map_ref S_AXI $bus
foreach {name physical type logical} {s_axi_aclk s_axi_aclk clock CLK s_axi_aresetn s_axi_aresetn reset RST} {
    set interface [ipx::add_bus_interface $name $core]
    set_property interface_mode slave $interface
    set_property bus_type_vlnv "xilinx.com:signal:$type:1.0" $interface
    set_property abstraction_type_vlnv "xilinx.com:signal:${type}_rtl:1.0" $interface
    set mapping [ipx::add_port_map $logical $interface];set_property physical_name $physical $mapping
}
set clock [ipx::get_bus_interfaces s_axi_aclk -of_objects $core]
foreach {name value} {ASSOCIATED_BUSIF S_AXI ASSOCIATED_RESET s_axi_aresetn FREQ_HZ 100000000} {
    set param [ipx::add_bus_parameter $name $clock];set_property value $value $param
}
set reset [ipx::get_bus_interfaces s_axi_aresetn -of_objects $core]
set param [ipx::add_bus_parameter POLARITY $reset];set_property value ACTIVE_LOW $param
ipx::create_xgui_files $core
ipx::update_checksums $core
ipx::check_integrity $core
ipx::save_core $core
# 严重消息由调用者解析本次真实日志；Vivado2024.1不存在get_messages命令。
puts "V3A_IP_PACKAGE_PASS"
close_project
