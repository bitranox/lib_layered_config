"""``import lib_layered_config`` does not import Rich; ``display_config`` is exported lazily.

Only ``display_config`` needs Rich (and rich-click), which cost about a third of the package's import
time for every program that only reads configuration. The package imports the display adapter on
first access to ``display_config``; importing it by name, reading it as an attribute and
``from lib_layered_config import *`` all still give the function.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import lib_layered_config
from lib_layered_config.adapters.display import display_config as adapter_display_config
from tests.support.os_markers import os_agnostic

_SOURCE_ROOT = str(Path(lib_layered_config.__file__).resolve().parents[1])


def _run(code: str) -> dict[str, object]:
    """Run *code* in a fresh interpreter that imports this checkout, and return the JSON it prints."""
    completed = subprocess.run(  # noqa: S603 - the test's own interpreter and its own literal code
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {_SOURCE_ROOT!r})\n{code}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    return json.loads(completed.stdout)


@os_agnostic
def test_importing_the_package_leaves_rich_and_the_display_adapter_unimported() -> None:
    result = _run(
        "import json, lib_layered_config\n"
        "print(json.dumps({'file': lib_layered_config.__file__, 'loaded': sorted(name for name in sys.modules"
        " if name.split('.')[0] in ('rich', 'rich_click', 'click')"
        " or name == 'lib_layered_config.adapters.display.rich')}))"
    )

    assert str(result["file"]).startswith(_SOURCE_ROOT)
    assert result["loaded"] == []


@os_agnostic
def test_reading_display_config_imports_the_adapter_on_first_access() -> None:
    result = _run(
        "import json, lib_layered_config\n"
        "function = lib_layered_config.display_config\n"
        "print(json.dumps({'module': function.__module__, 'rich': 'rich' in sys.modules}))"
    )

    assert result == {"module": "lib_layered_config.adapters.display.rich", "rich": True}


@os_agnostic
def test_star_import_still_provides_display_config() -> None:
    result = _run("import json\nfrom lib_layered_config import *\nprint(json.dumps({'has': callable(display_config)}))")

    assert result == {"has": True}


@os_agnostic
def test_display_config_by_name_and_by_attribute_is_the_adapter_function() -> None:
    # Imported here, not at the top: this import statement is the lazy path under test.
    from lib_layered_config import display_config

    assert display_config is adapter_display_config
    assert lib_layered_config.display_config is adapter_display_config


@os_agnostic
def test_an_unknown_attribute_still_raises_attribute_error() -> None:
    missing = "no_such_name"

    with pytest.raises(AttributeError, match="no attribute 'no_such_name'"):
        getattr(lib_layered_config, missing)
