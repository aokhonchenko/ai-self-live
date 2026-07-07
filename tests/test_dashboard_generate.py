import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "dashboard" / "generate.py"


def load_generate_module():
    sys.path.insert(0, str(MODULE_PATH.parent))
    spec = importlib.util.spec_from_file_location("dashboard_generate", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_find_project_root_accepts_dashboard_directory():
    module = load_generate_module()
    dashboard_dir = MODULE_PATH.parent

    assert module.find_project_root(str(dashboard_dir)) == MODULE_PATH.parents[2]


def test_find_project_root_accepts_script_file():
    module = load_generate_module()

    assert module.find_project_root(str(MODULE_PATH)) == MODULE_PATH.parents[2]