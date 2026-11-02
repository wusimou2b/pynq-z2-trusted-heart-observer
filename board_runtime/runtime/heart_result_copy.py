"""Exact shallow copies of registered plain frozen results; same guard bytecode.

Never register observations/records: their private normalization caches must
not survive dataclasses.replace. Unknown types/state/constructors keep replace.
"""
from dataclasses import fields,is_dataclass,replace
from types import FunctionType,MethodType

class ResultCopies:
    def __init__(self,*types):
        self.layouts={};self.hooks=[];self.fast=self.fallback=0;self.restored=False
        for cls in types:
            if (not is_dataclass(cls) or not cls.__dataclass_params__.frozen
                or not cls.__dataclass_params__.init or hasattr(cls,'__post_init__') or hasattr(cls,'__slots__')
                or cls.__new__ is not object.__new__ or cls.__getattribute__ is not object.__getattribute__
                or cls.__init__.__code__.co_filename!='<string>'):continue
            fs=fields(cls)
            if not all(f.init for f in fs) or len(fs)!=len(cls.__dataclass_fields__):continue
            self.layouts[cls]=frozenset(f.name for f in fs)

    def replace(self,obj,**changes):
        cls=type(obj);layout=self.layouts.get(cls)
        if layout is not None:
            data=vars(obj)
            if data.keys()==layout and changes.keys()<=layout:
                # replace is shallow too. No __post_init__/InitVar/custom init
                # is bypassed for these exact, verified generated result types.
                result=object.__new__(cls)
                result.__dict__.update(data);result.__dict__.update(changes)
                self.fast+=1;return result
        self.fallback+=1;return replace(obj,**changes)

    def install(self,obj,name):
        method=getattr(obj,name);original=getattr(method,'__func__',None)
        if original is None or original.__globals__.get('replace') is not replace:
            raise ValueError('original bound dataclasses.replace method required: '+name)
        namespace=dict(original.__globals__);namespace['replace']=self.replace
        cloned=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
        cloned.__kwdefaults__=original.__kwdefaults__
        before=(name in vars(obj),vars(obj).get(name))
        self.hooks.append((obj,name,*before));setattr(obj,name,MethodType(cloned,obj))

    def restore(self):
        while self.hooks:
            obj,name,present,value=self.hooks.pop()
            if present:setattr(obj,name,value)
            else:delattr(obj,name)
        self.restored=True

    def report(self):
        return dict(fast=self.fast,fallback=self.fallback,types=[c.__name__ for c in self.layouts],
            restored=self.restored,original_method_bytecode=True,original_guard_calls=True,
            observations_and_records_excluded=True)

def child_factory(factory,adapters):
    def make(base):
        original=factory(base)
        class Chain(original):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                from heart_v2.runtime_main_chain import RuntimeFrame
                from heart_v3a.runtime_pl_chain import PlRuntimeFrame
                adapter=ResultCopies(RuntimeFrame,PlRuntimeFrame);adapters.append(adapter)
                adapter.install(self,'_process');adapter.install(self,'_final_output')
        return Chain
    return make
