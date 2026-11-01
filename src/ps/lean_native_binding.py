"""Connect the qualified receipt library to the retained live GIL loader."""
import ctypes as C
from pathlib import Path


def bind_registered(library, registered, retained_bind):
    if __package__:
        from .fault_replay_native import ObservedLibrary
    else:
        from fault_replay_native import ObservedLibrary
    # Only an object produced by this installed scope's manifest-checked loader
    # may cross this boundary. Do not generally relax the old type guard.
    if type(library) is not ObservedLibrary or not any(library is item for item in registered):
        raise ValueError('manifest-validated registered receipt library required')
    storage = getattr(library, '_entry_storage', None)
    if not isinstance(storage, tuple) or len(storage) != 4:
        raise ValueError('preallocated first SAMPLE storage required')
    _, trace_library, state, receipt_call = storage
    if state['calls'] != 0:
        raise ValueError('first SAMPLE has already been consumed; no rebind')
    # Run the ORIGINAL strict SnapshotLibrary, ABI, same-address and GIL checks
    # on the actual underlying library, rather than on its observation wrapper.
    checked = retained_bind(library.original)
    receipt = library.held.hm_transact_sample_fault_receipt
    entry = trace_library.hm_transact_sample_entry_trace
    if Path(library.held._name).resolve() != Path(library.original.lib._name).resolve():
        raise ValueError('receipt and validated native binary differ')
    base_args = list(library.original.lib.hm_transact_sample.argtypes)
    for fn, args in ((receipt, base_args + [C.c_void_p, C.c_size_t]),
                     (entry, base_args + [C.c_void_p, C.c_size_t] * 2)):
        if (not isinstance(fn, C._CFuncPtr) or fn.argtypes != args
                or fn.restype is not C.c_int or not fn._flags_ & C._FUNCFLAG_PYTHONAPI):
            raise ValueError('qualified receipt/entry ABI or held GIL differs')
    if receipt_call is not receipt:
        raise ValueError('first SAMPLE ordinary receipt target differs')
    library._retained_gil_check = checked
    library.binding_info = dict(
        policy='hold_gil_receipt_first_sample_v1',
        retained_same_symbol_guard=dict(checked.binding_info),
        receipt_address=C.cast(receipt, C.c_void_p).value,
        entry_address=C.cast(entry, C.c_void_p).value,
        receipt_function_flags=receipt._flags_, entry_function_flags=entry._flags_,
        original_type_abi_address_guard_retained=True,
        ordinary_receipt_after_first=True, first_actual_sample_traced=True,
        preflight_sample_calls=0, new_per_sample_clocks=False,
        # The old reference report must not claim the two NEW observation
        # symbols are the original single symbol. Export actual provenance.
        original_single_symbol_report_applicable=False)
    return library
