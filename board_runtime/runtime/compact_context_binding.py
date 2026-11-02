"""Bind A3/C to the reviewed physical pair without rewriting observed identity."""
from types import FunctionType

OLD_PAIR=(
    '6dc798a77f8577629f5d824bf9081e994352b4cd104dde31b8b265c621bdd966',
    '3c44a48758fce3f1a581f8ae3d74d543a712b539d922fad8c739b4bd7a5b9393')
RELEASE_PAIR=(
    '0a91f3f16740edb5fb7f947945fa5c965b83efd298df9e00250c9934087a8f7c',
    'b652e060e8954e480ca03be4f90c239a83b0b131e6503fccf504d64d000a626a')


def paired_bind(original):
    """Keep the complete original binding, replacing its single pair constant."""
    constants=original.__code__.co_consts
    if sum(type(value) is tuple and value==OLD_PAIR for value in constants)!=1:
        raise ValueError('reviewed A3/C pair binding contract differs')
    updated=tuple(RELEASE_PAIR if type(value) is tuple and value==OLD_PAIR else value for value in constants)
    result=FunctionType(original.__code__.replace(co_consts=updated),original.__globals__,
        original.__name__,original.__defaults__,original.__closure__)
    result.__kwdefaults__=None if original.__kwdefaults__ is None else dict(original.__kwdefaults__)
    result.__qualname__,result.__module__,result.__doc__=original.__qualname__,original.__module__,original.__doc__
    return result
