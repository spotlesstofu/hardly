# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

from logging import getLogger
from os import getenv
from re import fullmatch
from typing import Optional

from hardly.handlers.abstract import TaskName
from ogr.abstract import GitProject, PullRequest
from packit.api import PackitAPI
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit.local_project import LocalProject
from packit_service.worker.events import MergeRequestGitlabEvent, PipelineGitlabEvent
from packit_service.worker.handlers import JobHandler
from packit_service.worker.handlers.abstract import (
    reacts_to,
)
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

        if not self.package_config:
            logger.debug("No package config found.")
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
        dg_mr_info = f"""###### Info for package maintainer
This MR has been automatically created from
[this source-git MR]({self.mr_url}).
Please review the contribution and once you are comfortable with the content,
you should trigger a CI pipeline run via `Pipelines → Run pipeline`."""
        dg_mr = self.api.sync_release(
            version=self.api.up.get_specfile_version(),
            title=self.mr_title,
            description=f"{self.mr_description}\n\n---\n{dg_mr_info}",
            sync_default_files=False,
            # we rely on this in PipelineHandler below
            local_pr_branch_suffix=f"src-{self.mr_identifier}",
        )

        if dg_mr:
            comment = f"""[Dist-git MR #{dg_mr.id}]({dg_mr.url})
has been created for sake of triggering the downstream checks.
It ensures that your contribution is valid and can be incorporated in CentOS Stream
as dist-git is still the authoritative source for the distribution.
We want to run checks there only so they don't need to be reimplemented in source-git as well."""
            self.project.get_pr(int(self.mr_identifier)).comment(comment)

        return TaskResults(success=True)


@reacts_to(event=PipelineGitlabEvent)
class PipelineHandler(JobHandler):
    task_name = TaskName.pipeline

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
        # It would ideally be taken from package_config.dist_git_namespace
        # instead of from getenv, but package_config is None because there's no config file.
        self.src_git_namespace: str = getenv("DISTGIT_NAMESPACE").replace(
            "/rpms", "/src"
        )
        # project name is expected to be the same in dist-git and src-git
        self.src_git_name: str = event["project_name"]
        # branch name
        self.git_ref: str = event["git_ref"]

        self.status: str = event["status"]
        self.detailed_status: str = event["detailed_status"]
        self.pipeline_url: str = (
            f"{event['project_url']}/-/pipelines/{event['pipeline_id']}"
        )

        # lazy
        self._src_git_project: Optional[GitProject] = None
        self._src_git_mr_id: Optional[int] = None
        self._src_git_mr: Optional[PullRequest] = None
        self._status_reporter: Optional[StatusReporter] = None

    @property
    def src_git_mr_id(self) -> Optional[int]:
        """
        https://docs.gitlab.com/ee/user/project/integrations/webhooks.html#pipeline-events
        suggests, there's a merge_request field containing relation to the (dist-git) MR.
        Sadly, it's not always true, as in our staging repos,
        in which case the merge_request info is empty.
        Luckily, we've stored the src-git MR in the branch name (self.git_ref)
        from which the dist-git MR is created.
        See how we set local_pr_branch_suffix in DistGitMRHandler.run()
        :return: src-git MR number or None if self.git_ref doesn't contain it
        """
        if not self._src_git_mr_id:
            # git_ref is expected in a form {version}-{dist_git_branch}-src-{mr_number}
            m = fullmatch(r".+-.+-src-(\d+)", self.git_ref)
            self._src_git_mr_id = int(m[1]) if m else None
        return self._src_git_mr_id

    @property
    def src_git_project(self) -> GitProject:
        if not self._src_git_project:
            self._src_git_project = self.project.service.get_project(
                namespace=self.src_git_namespace,
                repo=self.src_git_name,
            )
        return self._src_git_project

    @property
    def src_git_mr(self) -> PullRequest:
        if not self._src_git_mr:
            self._src_git_mr = self.src_git_project.get_pr(self.src_git_mr_id)
        return self._src_git_mr

    @property
    def status_reporter(self) -> StatusReporter:
        if not self._status_reporter:
            self._status_reporter = StatusReporter.get_instance(
                project=self.src_git_project,
                # The head_commit is latest commit of the MR.
                # If there was a new commit pushed before the pipeline ended, the report
                # might be incorrect until the new (for the new commit) pipeline finishes.
                commit_sha=self.src_git_mr.head_commit,
                pr_id=self.src_git_mr_id,
            )
        return self._status_reporter

    def run(self) -> TaskResults:
        """
        When a dist-git MR CI Pipeline changes status, create a commit
        status in the original src-git MR with a link to the Pipeline.
        """
        if not self.src_git_mr_id:
            logger.debug("Not a source-git related pipeline")
            return TaskResults(success=True, details={})

        pipeline_status_to_base_commit_status = {
            "success": BaseCommitStatus.success,
            "failed": BaseCommitStatus.failure,
            "pending": BaseCommitStatus.pending,
            "running": BaseCommitStatus.running,
        }

        # Our account(s) have no access (unless it's manually added) into the fork repos,
        # to set the commit status (which would look like a Pipeline result)
        # so the status reporter fallbacks to adding a commit comment.
        # To not pollute MRs with too many comments, we might later skip
        # the 'Pipeline is pending/running' events.
        self.status_reporter.set_status(
            state=pipeline_status_to_base_commit_status[self.status],
            description=f"Changed status to {self.detailed_status}.",
            check_name="Dist-git MR CI Pipeline",
            url=self.pipeline_url,
        )
        return TaskResults(success=True, details={})
