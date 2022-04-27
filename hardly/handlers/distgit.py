# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import re
from logging import getLogger
from os import getenv
from re import fullmatch
from typing import Optional

from hardly.handlers.abstract import TaskName
from ogr.abstract import PullRequest
from packit.api import PackitAPI
from packit.config.job_config import JobConfig
from packit.config.package_config import PackageConfig
from packit.local_project import LocalProject
from packit_service.models import PullRequestModel, SourceGitPRDistGitPRModel
from packit_service.worker.events import MergeRequestGitlabEvent, PipelineGitlabEvent
from packit_service.worker.events.pagure import PullRequestFlagPagureEvent
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
        self.mr_identifier = event["identifier"]
        self.mr_title = event["title"]
        self.mr_description = event["description"]
        self.mr_url = event["url"]
        self.source_project_url = event["source_project_url"]
        self.target_repo = (
            f"{event['target_repo_namespace']}/{event['target_repo_name']}"
        )
        self.target_repo_branch = event["target_repo_branch"]

        # lazy
        self._source_git_pr_model = None
        self._dist_git_pr_model = None
        self._dist_git_pr = None

    @property
    def source_git_pr_model(self) -> PullRequestModel:
        if not self._source_git_pr_model:
            self._source_git_pr_model = PullRequestModel.get_or_create(
                pr_id=self.mr_identifier,
                namespace=self.project.namespace,
                repo_name=self.project.repo,
                project_url=self.project.get_web_url(),
            )
        return self._source_git_pr_model

    @property
    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        if not self._dist_git_pr_model:
            if sg_dg := SourceGitPRDistGitPRModel.get_by_source_git_id(
                self.source_git_pr_model.id
            ):
                self._dist_git_pr_model = sg_dg.dist_git_pull_request
        return self._dist_git_pr_model

    @property
    def dist_git_pr(self) -> Optional[PullRequest]:
        if not self._dist_git_pr and self.dist_git_pr_model:
            dist_git_project = self.service_config.get_project(
                url=self.dist_git_pr_model.project.project_url
            )
            self._dist_git_pr = dist_git_project.get_pr(self.dist_git_pr_model.pr_id)
        return self._dist_git_pr

    def run(self) -> TaskResults:
        """
        If user creates a merge-request on the source-git repository,
        create a matching merge-request to the dist-git repository.
        """
        if not self.handle_target():
            logger.debug(
                "Not creating a dist-git MR from "
                f"{self.target_repo}:{self.target_repo_branch}"
            )
            return TaskResults(success=True, details={})

        if not self.package_config:
            logger.debug("No package config found.")
            return TaskResults(success=True, details={})

        if self.dist_git_pr_model:
            # The source-git PR was probably closed and then reopened
            logger.info(
                f"{self.source_git_pr_model} already has corresponding {self.dist_git_pr_model}"
            )
            if self.dist_git_pr:
                # TODO: reopen the corresponding dist-git PR as well if it's already closed
                # https://github.com/packit/ogr/pull/714
                comment = f"[Source-git MR]({self.mr_url}) has been reopened."
                self.dist_git_pr.comment(comment)
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
        dg_mr_info = f"""###### Info for package maintainer
This MR has been automatically created from
[this source-git MR]({self.mr_url})."""
        if getenv("PROJECT", "").startswith("stream"):
            dg_mr_info += """
Please review the contribution and once you are comfortable with the content,
you should trigger a CI pipeline run via `Pipelines → Run pipeline`."""

        if (
            self.target_repo_branch
            in self.api.dg.local_project.git_project.get_branches()
        ):
            dist_git_branch = self.target_repo_branch
        else:
            msg = f"""
Downstream {self.target_repo}:{self.target_repo_branch} branch does not exist.
"""
            self.project.get_pr(int(self.mr_identifier)).comment(msg)
            logger.debug(msg)
            dist_git_branch = None

        dg_mr = None
        if dist_git_branch:
            logger.info(
                f"About to create a dist-git MR from source-git MR {self.mr_url}"
            )
            dg_mr = self.api.sync_release(
                dist_git_branch=dist_git_branch,
                version=self.api.up.get_specfile_version(),
                add_new_sources=False,
                title=self.mr_title,
                description=f"{self.mr_description}\n\n---\n{dg_mr_info}",
                sync_default_files=False,
                # we rely on this in PipelineHandler below
                local_pr_branch_suffix=f"src-{self.mr_identifier}",
                mark_commit_origin=True,
            )

        if dg_mr:
            comment = f"""[Dist-git MR #{dg_mr.id}]({dg_mr.url})
has been created for sake of triggering the downstream checks.
It ensures that your contribution is valid and can be incorporated in
dist-git as it is still the authoritative source for the distribution.
We want to run checks there only so they don't need to be reimplemented in source-git as well."""
            self.project.get_pr(int(self.mr_identifier)).comment(comment)

            SourceGitPRDistGitPRModel.get_or_create(
                self.mr_identifier,
                self.project.namespace,
                self.project.repo,
                self.project.get_web_url(),
                dg_mr.id,
                dg_mr.target_project.namespace,
                dg_mr.target_project.repo,
                dg_mr.target_project.get_web_url(),
            )

        return TaskResults(success=True)

    def handle_target(self) -> bool:
        """Tell if a target repo and branch pair of an MR should be handled or ignored."""
        handled_targets = self.service_config.gitlab_mr_targets_handled

        # If nothing is configured, all targets are handled.
        if not handled_targets:
            return True

        for target in handled_targets:
            if re.fullmatch(target.repo or ".+", self.target_repo) and re.fullmatch(
                target.branch or ".+", self.target_repo_branch
            ):
                return True
        return False


class SyncFromDistGitPRHandler(JobHandler):
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

        self.status_state: Optional[BaseCommitStatus] = None
        self.status_description: Optional[str] = None
        self.status_check_name: Optional[str] = None
        self.status_url: Optional[str] = None

    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        raise NotImplementedError("This should have been implemented.")

    def run(self) -> TaskResults:
        """
        When a dist-git PR flag/pipeline is updated, create a commit
        status in the original source-git MR with the flag/pipeline info.
        """
        if not (dist_git_pr_model := self.dist_git_pr_model()):
            logger.debug("No dist-git PR model.")
            return TaskResults(success=True, details={})
        if not (
            sg_dg := SourceGitPRDistGitPRModel.get_by_dist_git_id(dist_git_pr_model.id)
        ):
            logger.debug(f"Source-git PR for {dist_git_pr_model} not found.")
            return TaskResults(success=True, details={})

        source_git_pr_model = sg_dg.source_git_pull_request
        source_git_project = self.service_config.get_project(
            url=source_git_pr_model.project.project_url
        )
        source_git_pr = source_git_project.get_pr(source_git_pr_model.pr_id)

        status_reporter = StatusReporter.get_instance(
            project=source_git_project,
            # The head_commit is the latest commit of the MR.
            # If there was a new commit pushed before the pipeline ended, the report
            # might be incorrect until the new (for the new commit) pipeline finishes.
            commit_sha=source_git_pr.head_commit,
            pr_id=source_git_pr.id,
        )
        # Our account(s) have no access (unless it's manually added) into the fork repos,
        # to set the commit status (which would look like a Pipeline result)
        # so the status reporter fallbacks to adding a commit comment.
        # To not pollute MRs with too many comments, we might later skip
        # the 'Pipeline is pending/running' events.
        # See also https://github.com/packit/packit-service/issues/1411
        status_reporter.set_status(
            state=self.status_state,
            description=self.status_description,
            check_name=self.status_check_name,
            url=self.status_url,
        )
        return TaskResults(success=True, details={})


@reacts_to(event=PipelineGitlabEvent)
class SyncFromGitlabMRHandler(SyncFromDistGitPRHandler):
    task_name = TaskName.sync_from_gitlab_mr

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

        # https://docs.gitlab.com/ee/api/pipelines.html#list-project-pipelines -> status
        self.status_state: BaseCommitStatus = {
            "pending": BaseCommitStatus.pending,
            "created": BaseCommitStatus.pending,
            "waiting_for_resource": BaseCommitStatus.pending,
            "preparing": BaseCommitStatus.pending,
            "scheduled": BaseCommitStatus.pending,
            "manual": BaseCommitStatus.pending,
            "running": BaseCommitStatus.running,
            "success": BaseCommitStatus.success,
            "skipped": BaseCommitStatus.success,
            "failed": BaseCommitStatus.failure,
            "canceled": BaseCommitStatus.failure,
        }[event["status"]]
        self.status_description: str = f"Changed status to {event['detailed_status']}"
        self.status_check_name: str = "Dist-git MR CI Pipeline"
        self.status_url: str = (
            f"{event['project_url']}/-/pipelines/{event['pipeline_id']}"
        )
        self.source: str = event["source"]
        self.merge_request_url: str = event["merge_request_url"]

    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        if self.source == "merge_request_event":
            # Derive project from merge_request_url because
            # self.project can be either source or target
            m = fullmatch(r"(\S+)/-/merge_requests/(\d+)", self.merge_request_url)
            if m:
                project = self.service_config.get_project(url=m[1])
                return PullRequestModel.get_or_create(
                    pr_id=int(m[2]),
                    namespace=project.namespace,
                    repo_name=project.repo,
                    project_url=m[1],
                )
        return None


@reacts_to(event=PullRequestFlagPagureEvent)
class SyncFromPagurePRHandler(SyncFromDistGitPRHandler):
    task_name = TaskName.sync_from_pagure_pr

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

        # https://pagure.io/api/0/#pull_requests-tab -> "Flag a pull-request" -> status
        self.status_state = {
            "pending": BaseCommitStatus.pending,
            "success": BaseCommitStatus.success,
            "error": BaseCommitStatus.error,
            "failure": BaseCommitStatus.failure,
            "canceled": BaseCommitStatus.failure,
        }[event["status"]]
        self.status_description = event["comment"]
        self.status_check_name = event["username"]
        self.status_url = event["url"]

    def dist_git_pr_model(self) -> Optional[PullRequestModel]:
        return self.data.db_trigger
