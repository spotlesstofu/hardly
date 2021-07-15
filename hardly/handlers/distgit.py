# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
from logging import getLogger

from packit.config.job_config import JobConfig

from packit.config.package_config import PackageConfig

from hardly.handlers.abstract import TaskName
from packit_service.worker.events import MergeRequestGitlabEvent
from packit_service.worker.handlers import JobHandler
from packit_service.worker.handlers.abstract import reacts_to
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


# @configured_as(job_type=JobType.dist_git_pr)  # Requires a change in packit
@reacts_to(event=MergeRequestGitlabEvent)
class DistGitPRHandler(JobHandler):
    task_name = TaskName.dist_git_pr

    def __init__(
        self,
        package_config: PackageConfig,
        job_config: JobConfig,
        event: dict,
    ):
        super().__init__(
            package_config=package_config,
            job_config=job_config,
            event=event,
        )

    def run(self) -> TaskResults:
        """
        If user creates a merge-request on the source-git repository,
        create a matching merge-request to the dist-git repository.
        """

        logger.debug(
            "RUNNING DistGitPRHandler, Implement me !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        )
        return TaskResults(success=True, details={})
