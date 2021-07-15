# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from enum import Enum
from logging import getLogger

logger = getLogger(__name__)


class TaskName(str, Enum):
    copr_build_start = "task.run_copr_build_start_handler"
    copr_build_end = "task.run_copr_build_end_handler"
    copr_build = "task.run_copr_build_handler"
    dist_git_pr = "task.run_dist_git_pr_handler"
