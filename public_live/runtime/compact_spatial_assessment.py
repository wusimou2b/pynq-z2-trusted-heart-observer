"""Retain existing spatial/hybrid audits with the actual integrated identity."""
if __package__:
    from . import shadow_assessment
    from .hybrid_assessment import audit_artifacts as original_audit
    from .joint_startup import replace_attribute
else:
    import shadow_assessment
    from hybrid_assessment import audit_artifacts as original_audit
    from joint_startup import replace_attribute

OWNER_METADATA=dict(windows=16,spatial_version=0x20000,grid=[4,3],one_nlms_state=True,
    three_video_dma_preserved=True,main_sample_base=0x43ca0000)
original_assess_video=shadow_assessment.assess_spatial_video


def assess_video(report):
    gates=original_assess_video(report)
    identity=(report.get('identity') or {}).get('joint_identity') or {}
    gates['joint_identity']=bool(identity.get('nlms_axi_0')==dict(id=0x4e4c3304,version=0x10000)
        and identity.get('vision_0')==dict(id=0x56334232,version=0x20000)
        and identity.get('main_heart_sample')==dict(id=0x484d3235,version=0x20001)
        and identity.get('metadata')==OWNER_METADATA)
    return gates


def audit_artifacts(directory,summary,owner):
    with replace_attribute(shadow_assessment,'assess_spatial_video',assess_video):
        return original_audit(directory,summary,owner)
