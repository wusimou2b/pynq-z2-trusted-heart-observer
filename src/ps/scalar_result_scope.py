"""Cheaper copies of exact immutable result classes; retain guard bytecode."""
from contextlib import contextmanager
from heart_result_copy import ResultCopies


@contextmanager
def owner_copies(session):
    from heart_v2.runtime_main_chain import RuntimeFrame
    from heart_v3a.runtime_pl_chain import PlRuntimeFrame
    from v3a_25hz_live.contracts import ProcessedSlot
    copies = ResultCopies(RuntimeFrame, PlRuntimeFrame, ProcessedSlot)
    if len(copies.layouts) != 3:
        raise ValueError('exact owner result layouts differ')
    try:
        copies.install(session, '_guard_result')
        copies.install(session._safety, 'guard')
        copies.install(session, '_process_loop')
        yield copies
    finally:
        copies.restore()


def child_factory(factory, adapters):
    def make(base):
        original = factory(base)
        class Chain(original):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                from heart_v2.runtime_main_chain import RuntimeFrame
                copies = ResultCopies(RuntimeFrame)
                if len(copies.layouts) != 1:
                    raise ValueError('exact child result layout differs')
                adapters.append(copies)
                copies.install(self, '_final_output')
        return Chain
    return make


@contextmanager
def child_copies():
    import main_tail_compact
    from joint_startup import replace_attribute
    adapters = []
    try:
        with replace_attribute(main_tail_compact, 'make_chain',
                               child_factory(main_tail_compact.make_chain, adapters)):
            yield adapters
    finally:
        for copies in reversed(adapters):
            copies.restore()
