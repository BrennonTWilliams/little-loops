# >>> ll-spike-verdict hook >>>
import pytest as _ll_pytest


@_ll_pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    yield
    if call.when != "call" or call.excinfo is None:
        return
    exc = call.excinfo.value
    is_assertion = isinstance(exc, AssertionError) or (
        isinstance(exc, _ll_pytest.fail.Exception)
        and str(exc).startswith(("DID NOT RAISE", "DID NOT WARN"))
    )
    item.user_properties.append(("ll_exc_type", call.excinfo.type.__name__))
    item.user_properties.append(("ll_assertion", "true" if is_assertion else "false"))


# <<< ll-spike-verdict hook <<<
