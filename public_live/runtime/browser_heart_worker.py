"""Use the unchanged recovered shared hardware owner with the new package check."""
if __package__:
    from .joint_startup import replace_attribute
else:
    from joint_startup import replace_attribute


def verify_package(root):
    if __package__:from .browser_heart_guard import verify_package as verify
    else:from browser_heart_guard import verify_package as verify
    return verify(root)


def worker(*args, release_contract=None):
    if __package__:from . import heart_video_worker as original
    else:import heart_video_worker as original
    if release_contract is not None:
        return original.worker(*args, release_contract=release_contract)
    with replace_attribute(original,'verify_package',verify_package):
        return original.worker(*args)


def start_owner(context,*args):
    child=context.Process(target=worker,args=args,name='joint25-browser-waveform-owner',daemon=False)
    child.start()
    return child
