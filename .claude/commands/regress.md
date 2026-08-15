---
description: Turn a bug just found into a permanent regression test
---

Turn this failure into a regression test: $ARGUMENTS

Procedure:

1. Write the test **first**, in `tests/regression/`, and confirm it **fails**
   against current code. A regression test that passes before the fix is not
   testing what you think it is.
2. Name it `test_adrNNNN_*.py` when it pins an ADR, and add
   `pytestmark = pytest.mark.regression`.
3. The module docstring states the **symptom that was observed**, not just the
   rule. Someone reading it in a year needs to know what went wrong.
4. The assertion message names the ADR or invariant being violated, so a future
   failure explains itself.
5. Where useful, add a test that demonstrates the *original wrong behaviour*
   still fails — this keeps the guard's referent alive.
6. Only then apply the fix, and show me the test going red to green.

Do not weaken or skip any existing test in the process.
