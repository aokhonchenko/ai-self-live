import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_runtest_setup(item):
    module = getattr(item, "module", None)
    runner = getattr(module, "run_session", None)

    if runner is None or getattr(runner, "_test_root_wrapper_installed", False):
        return

    original_main = runner.main

    def main_with_root_override():
        root_override = getattr(runner, "ROOT_OVERRIDE", None)
        if root_override is None:
            return original_main()

        original_file = runner.__file__
        runner.__file__ = str(root_override / "scripts" / "run_session.py")
        try:
            return original_main()
        finally:
            runner.__file__ = original_file

    runner.main = main_with_root_override
    runner._test_root_wrapper_installed = True
