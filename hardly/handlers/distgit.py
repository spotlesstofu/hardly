# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from typing import Optional

from hardly.handlers.abstract import TaskName
from packit.api import PackitAPI
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit.local_project import LocalProject
from packit_service.worker.events import MergeRequestGitlabEvent
from packit_service.worker.handlers import JobHandler
from packit_service.worker.handlers.abstract import reacts_to
from packit_service.worker.reporting import StatusReporter, BaseCommitStatus
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

        self._status_reporter: Optional[StatusReporter] = None

    @property
    def status_reporter(self) -> StatusReporter:
        if not self._status_reporter:
            self._status_reporter = StatusReporter.get_instance(
                self.project, self.data.commit_sha, self.data.pr_id
            )
        return self._status_reporter

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

        logger.debug(f"About to create a dist-git MR from source-git MR {self.mr_url}")

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

            self.status_reporter.set_status(
                state=BaseCommitStatus.success,
                description="Dist-git MR created.",
                check_name=f"rpms#{dg_mr.url.split('/')[-1]}",
                url=dg_mr.url,
            )

        return TaskResults(success=True, details=details)


# @reacts_to(event=PipelineGitlabEvent)  # to be implemented in p-s
class PipelineHandler(JobHandler):
    task_name = TaskName.pipeline

    def run(self) -> TaskResults:
        """
        This docstring is a result of 'spike' about how to sync dist-git MR
        pipeline results back to the source-git MR.

        The notification about a change of a pipeline's status would be sent via
        a group webhook (with "Pipeline events" trigger) manually added to the
        redhat/centos-stream/rpms group.
        For staging, we'll hopefully have similarly configured
        redhat/centos-stream/staging/rpms group,
        otherwise a project webhook would need to be added to forks in
        packit-as-a-service-stg namespace, because that's where a pipeline
        runs in case of non-premium plan.

        The Pipeline event sent to a webhook contains:
        - project name
        - ref: branch name, which contains number of the original source-git MR
        The source-git namespace can be derived from
        package_config.dist_git_namespace.rstrip("/rpms")
        In case there's anything missing, we'd need to store the mapping info
        into DB when creating the dist-git MR.

        There's probably no way we can manually re-construct the whole pipeline from dist-git MR
        in the source-git MR without running it,
        but we can set a commit status with all the necessary information
        (or at least a link to the dist-git MR pipeline).
        """
        raise NotImplementedError()
