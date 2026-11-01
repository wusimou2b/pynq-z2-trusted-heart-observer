# Definitional proc to organize widgets for parameters.
proc init_gui { IPINST } {
  ipgui::add_param $IPINST -name "Component_Name"
  #Adding Page
  set Page_0 [ipgui::add_page $IPINST -name "Page 0"]
  ipgui::add_param $IPINST -name "IMAGE_HEIGHT" -parent ${Page_0}
  ipgui::add_param $IPINST -name "IMAGE_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "ROI_HEIGHT" -parent ${Page_0}
  ipgui::add_param $IPINST -name "ROI_WIDTH" -parent ${Page_0}
  ipgui::add_param $IPINST -name "ROI_X" -parent ${Page_0}
  ipgui::add_param $IPINST -name "ROI_Y" -parent ${Page_0}


}

proc update_PARAM_VALUE.IMAGE_HEIGHT { PARAM_VALUE.IMAGE_HEIGHT } {
	# Procedure called to update IMAGE_HEIGHT when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.IMAGE_HEIGHT { PARAM_VALUE.IMAGE_HEIGHT } {
	# Procedure called to validate IMAGE_HEIGHT
	return true
}

proc update_PARAM_VALUE.IMAGE_WIDTH { PARAM_VALUE.IMAGE_WIDTH } {
	# Procedure called to update IMAGE_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.IMAGE_WIDTH { PARAM_VALUE.IMAGE_WIDTH } {
	# Procedure called to validate IMAGE_WIDTH
	return true
}

proc update_PARAM_VALUE.ROI_HEIGHT { PARAM_VALUE.ROI_HEIGHT } {
	# Procedure called to update ROI_HEIGHT when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.ROI_HEIGHT { PARAM_VALUE.ROI_HEIGHT } {
	# Procedure called to validate ROI_HEIGHT
	return true
}

proc update_PARAM_VALUE.ROI_WIDTH { PARAM_VALUE.ROI_WIDTH } {
	# Procedure called to update ROI_WIDTH when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.ROI_WIDTH { PARAM_VALUE.ROI_WIDTH } {
	# Procedure called to validate ROI_WIDTH
	return true
}

proc update_PARAM_VALUE.ROI_X { PARAM_VALUE.ROI_X } {
	# Procedure called to update ROI_X when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.ROI_X { PARAM_VALUE.ROI_X } {
	# Procedure called to validate ROI_X
	return true
}

proc update_PARAM_VALUE.ROI_Y { PARAM_VALUE.ROI_Y } {
	# Procedure called to update ROI_Y when any of the dependent parameters in the arguments change
}

proc validate_PARAM_VALUE.ROI_Y { PARAM_VALUE.ROI_Y } {
	# Procedure called to validate ROI_Y
	return true
}


proc update_MODELPARAM_VALUE.IMAGE_WIDTH { MODELPARAM_VALUE.IMAGE_WIDTH PARAM_VALUE.IMAGE_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.IMAGE_WIDTH}] ${MODELPARAM_VALUE.IMAGE_WIDTH}
}

proc update_MODELPARAM_VALUE.IMAGE_HEIGHT { MODELPARAM_VALUE.IMAGE_HEIGHT PARAM_VALUE.IMAGE_HEIGHT } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.IMAGE_HEIGHT}] ${MODELPARAM_VALUE.IMAGE_HEIGHT}
}

proc update_MODELPARAM_VALUE.ROI_X { MODELPARAM_VALUE.ROI_X PARAM_VALUE.ROI_X } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.ROI_X}] ${MODELPARAM_VALUE.ROI_X}
}

proc update_MODELPARAM_VALUE.ROI_Y { MODELPARAM_VALUE.ROI_Y PARAM_VALUE.ROI_Y } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.ROI_Y}] ${MODELPARAM_VALUE.ROI_Y}
}

proc update_MODELPARAM_VALUE.ROI_WIDTH { MODELPARAM_VALUE.ROI_WIDTH PARAM_VALUE.ROI_WIDTH } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.ROI_WIDTH}] ${MODELPARAM_VALUE.ROI_WIDTH}
}

proc update_MODELPARAM_VALUE.ROI_HEIGHT { MODELPARAM_VALUE.ROI_HEIGHT PARAM_VALUE.ROI_HEIGHT } {
	# Procedure called to set VHDL generic/Verilog parameter value(s) based on TCL parameter value
	set_property value [get_property value ${PARAM_VALUE.ROI_HEIGHT}] ${MODELPARAM_VALUE.ROI_HEIGHT}
}

