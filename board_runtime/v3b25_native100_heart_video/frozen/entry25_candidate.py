"""One predeclared offline candidate; never patch the frozen runtime in place."""
import ast
import inspect
import textwrap

from peak_chain import PeakTimingChain
from v3a_rate25.benefit import Selector25


def _private_step():
    tree = ast.parse(textwrap.dedent(inspect.getsource(Selector25.step)))
    matches = [node for node in ast.walk(tree)
               if isinstance(node, ast.Compare)
               and isinstance(node.left, ast.Attribute)
               and isinstance(node.left.value, ast.Name)
               and node.left.value.id == 'self'
               and node.left.attr == 'good_checks']
    if len(matches) != 1:
        raise RuntimeError('Frozen entry comparison is not unique')
    compare = matches[0]
    if (len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.GtE)
            or len(compare.comparators) != 1
            or not isinstance(compare.comparators[0], ast.Constant)
            or compare.comparators[0].value != 2):
        raise RuntimeError('Frozen entry rule is not the expected >= 2')
    compare.comparators[0].value = 6
    namespace = dict(Selector25.step.__globals__)
    exec(compile(tree, '<offline-six-check-entry>', 'exec'), namespace)
    return namespace['step'], ast.unparse(tree)


_step, CANDIDATE_STEP_SOURCE = _private_step()


class DelayedSelector25(Selector25):
    step = _step


class DelayedPeakChain(PeakTimingChain):
    def _reset_signals(self):
        super()._reset_signals()
        self.selector = DelayedSelector25()
