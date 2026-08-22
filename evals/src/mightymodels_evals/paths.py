from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR.joinpath('templates')
REPORT_TEMPLATE = PACKAGE_DIR.joinpath('report_template.html')
EVALS_ROOT = PACKAGE_DIR.parents[1]


def template_dir(name: str) -> Path:
    return TEMPLATES_DIR.joinpath(name)


def overlay_dir(name: str) -> Path:
    return TEMPLATES_DIR.joinpath('overlays', name)
