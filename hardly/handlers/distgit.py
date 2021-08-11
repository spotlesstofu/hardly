# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
from logging import getLogger

from hardly.handlers.abstract import TaskName
from packit.api import PackitAPI
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit.local_project import LocalProject
from packit_service.worker.events import MergeRequestGitlabEvent
from packit_service.worker.handlers import JobHandler
from packit_service.worker.handlers.abstract import reacts_to
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


# @configured_as(job_type=JobType.dist_git_pr)  # Requires a change in packit
@reacts_to(event=MergeRequestGitlabEvent)
class DistGitMRHandler(JobHandler):
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
        self.mr_identifier = event.get("identifier")
        self.mr_title = event.get("title")
        self.mr_description = event.get("description")
        self.mr_url = event.get("url")
        self.source_project_url = event.get("source_project_url")
        self.target_repo_branch = event.get("target_repo_branch")

    def run(self) -> TaskResults:
        """
        If user creates a merge-request on the source-git repository,
        create a matching merge-request to the dist-git repository.
        """
        if self.target_repo_branch != "c9s":
            logger.debug(
                f"Not creating a dist-git MR from {self.target_repo_branch} branch"
            )
            return TaskResults(success=True, details={})

        source_project = self.service_config.get_project(url=self.source_project_url)
        self.local_project = LocalProject(
            git_project=source_project,
            ref=self.data.commit_sha,
            working_dir=self.service_config.command_handler_work_dir,
        )

        self.api = PackitAPI(
            config=self.service_config,
            package_config=self.package_config,
            upstream_local_project=self.local_project,
        )

        dg_mr = self.api.sync_release(
            version=self.api.up.get_specfile_version(),
            title=self.mr_title,
            description=f"{self.mr_description}\n\n\nSee: {self.mr_url}",
            sync_default_files=False,
            local_pr_branch_suffix=f"src-{self.mr_identifier}",
        )

        details = {}
        if dg_mr:
            details["msg"] = f"MR created: {dg_mr.url}"
        return TaskResults(success=True, details=details)
