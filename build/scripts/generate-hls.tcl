# Generate external tool-owned RTL locally from the bundled BSD C++ sources.
# No device connection. Do not replace the separately qualified runtime assets.
if {![info exists env(THO_BUILD_SESSION)] || ![info exists env(THO_HLS_CORE)]} {error "Expected THO_BUILD_SESSION and THO_HLS_CORE"}
set session [file normalize $env(THO_BUILD_SESSION)]
set core $env(THO_HLS_CORE)
if {$core ni {color_convert pixel_unpack}} {error "Unsupported HLS core"}
cd "$session/hls_work"
set sources "../hls_sources/$core"
open_project $core
set_top $core
add_files "$sources/$core.cpp"
add_files -tb "$sources/${core}_test.cpp"
open_solution "solution1" -flow_target vivado
set_part {xc7z020clg400-1}
create_clock -period 7
csim_design
csynth_design
export_design -format ip_catalog -vendor xilinx.com -library hls -version 1.0 -output "$session/hls_work/${core}_ip.zip"
close_project
exit
