"""Explicitly called binding example. Importing this file does not import PYNQ.

Call make_driver with pynq.DefaultIP only during authorized board integration.
Creating a DefaultIP instance can map registers; this is not an offline probe.
"""


def make_driver(default_ip_class, *, vlnv, readable_registers):
    if not isinstance(vlnv, str) or len(vlnv.split(':')) != 4 or any(not part or part.strip() != part for part in vlnv.split(':')):
        raise ValueError('an exact VLNV is required')
    registers = dict(readable_registers)
    for name, offset in registers.items():
        if not isinstance(name, str) or not name or type(offset) is not int or offset < 0 or offset % 4:
            raise ValueError('registers must be named, aligned nonnegative byte offsets')

    class ProfileIP(default_ip_class):
        bindto = [vlnv]

        def __init__(self, description):
            if not isinstance(description, dict) or description.get('type') != vlnv:
                raise ValueError('IP VLNV differs')
            size = description.get('addr_range')
            if type(size) is not int or size <= 0 or any(offset + 4 > size for offset in registers.values()):
                raise ValueError('register not within declared address range')
            super().__init__(description)

        def read_declared(self, name):
            # Caller must declare only registers documented as side-effect-free.
            # No scan or generic write method is introduced by this example.
            return self.read(registers[name])

    return ProfileIP
