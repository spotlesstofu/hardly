# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).parent
DATA_DIR = TESTS_DIR / "data"


def first_dict_value(a_dict: dict) -> Any:
    return a_dict[next(iter(a_dict))]
