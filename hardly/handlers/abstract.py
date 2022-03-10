# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from enum import Enum


class TaskName(str, Enum):
    dist_git_pr = "task.run_dist_git_pr_handler"
    sync_from_gitlab_mr = "task.run_sync_from_gitlab_mr_handler"
    sync_from_pagure_pr = "task.run_sync_from_pagure_pr_handler"
