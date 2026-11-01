"""Instance-local scalar conversion; the original journal bytecode stays intact."""
from dataclasses import fields
from types import FunctionType, MethodType


def make_converter(frame_type, runtime_type, original_asdict):
    frame_names=tuple(field.name for field in fields(frame_type))
    runtime_names=tuple(field.name for field in fields(runtime_type))
    if runtime_names.count('frame')!=1:
        raise ValueError('runtime must contain one frame')
    scalar_types=frozenset((int,float,bool,str,type(None)))

    def convert(runtime):
        if type(runtime) is not runtime_type or type(runtime.frame) is not frame_type:
            return original_asdict(runtime)
        frame={name:getattr(runtime.frame,name) for name in frame_names}
        result={name:frame if name=='frame' else getattr(runtime,name) for name in runtime_names}
        if any(type(value) not in scalar_types for value in frame.values()) or any(
                type(value) not in scalar_types for name,value in result.items() if name!='frame'):
            return original_asdict(runtime)
        return result
    return convert


class JournalAdapter:
    def __init__(self):
        self._journal=None
        self._previous=None
        self._had_attribute=False
        self._installed=False
        self._restored=False
        self._method=None
        self._rollback_error=None

    def install(self,journal,frame_type,runtime_type):
        if self._journal is not None:
            raise RuntimeError('journal adapter already used')
        original=journal.save_result.__func__
        namespace=dict(original.__globals__)
        namespace['asdict']=make_converter(frame_type,runtime_type,namespace['asdict'])
        cloned=FunctionType(original.__code__,namespace,original.__name__,
                            original.__defaults__,original.__closure__)
        cloned.__kwdefaults__=original.__kwdefaults__
        self._journal=journal
        self._had_attribute='save_result' in vars(journal)
        self._previous=vars(journal).get('save_result')
        self._method=MethodType(cloned,journal)
        try:
            journal.save_result=self._method
            self._installed=True
        except BaseException:
            try: self.restore()
            except BaseException as exc:
                self._rollback_error=dict(type=type(exc).__name__,message=str(exc))
            raise

    def restore(self):
        if self._journal is None or self._restored:
            return
        if self._had_attribute:
            self._journal.save_result=self._previous
        elif 'save_result' in vars(self._journal):
            del self._journal.save_result
        self._restored=True

    def report(self):
        return dict(installed=self._installed,restored=self._restored,
                    active=self._journal is not None and vars(self._journal).get('save_result') is self._method,
                    rollback_error=self._rollback_error,
                    original_method_bytecode_preserved=True,
                    module_and_class_unchanged=True)
