"""Explicit PYNQ hierarchy binding example; no hardware imports at module load."""


def make_hierarchy_driver(default_hierarchy_class, *, required_ips):
    required = dict(required_ips)
    if not required or any(not isinstance(k, str) or not k or '/' in k or not isinstance(v, str) or len(v.split(':')) != 4 or any(not p or p.strip() != p for p in v.split(':')) for k,v in required.items()):
        raise ValueError('direct child instance names and exact VLNVs required')

    class ProfileHierarchy(default_hierarchy_class):
        @staticmethod
        def checkhierarchy(description):
            if not isinstance(description, dict):
                return False
            ip = description.get('ip', {})
            return isinstance(ip, dict) and all(isinstance(ip.get(k), dict) and ip[k].get('type') == v for k,v in required.items())

        def __init__(self, description):
            if not self.checkhierarchy(description):
                raise ValueError('hierarchy required IP capabilities differ')
            super().__init__(description)

    return ProfileHierarchy
