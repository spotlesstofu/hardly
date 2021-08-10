# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import json
import pytest
from tests.spellbook import DATA_DIR


@pytest.fixture(scope="module")
def mr_event():
    return json.loads((DATA_DIR / "webhooks" / "gitlab" / "mr_event.json").read_text())
