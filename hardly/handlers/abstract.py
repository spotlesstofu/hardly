# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from enum import Enum
from logging import getLogger

logger = getLogger(__name__)


class TaskName(str, Enum):
    dist_git_pr = "task.run_dist_git_pr_handler"
    pipeline = "task.run_pipeline_handler"
