# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
import pytest
from flexmock import flexmock

from hardly.handlers import SyncFromPagurePRHandler, SyncFromGitlabMRHandler
from packit_service.config import ServiceConfig
from packit_service.models import SourceGitPRDistGitPRModel
from packit_service.worker.events.pagure import PullRequestFlagPagureEvent
from packit_service.worker.parser import Parser
from packit_service.worker.reporting import (
    BaseCommitStatus,
    StatusReporter,
)


@pytest.mark.parametrize(
    "event, src_project_url, status_state, status_description, status_check_name, status_url",
    [
        pytest.param(
            "fedora_dg_pr_flag_updated_event",
            "https://gitlab.com/fedora/src/python-httpretty",
            BaseCommitStatus.success,
            "Jobs result is success",
            "Zuul",
            "https://fedora.softwarefactory-project.io/"
            "zuul/buildset/b6d1c4f0b1db49428bc594cf74307ec6",
            id="Fedora Pagure flag",
        ),
        pytest.param(
            "pipeline_event",
            "https://gitlab.com/packit-service/src/open-vm-tools",
            BaseCommitStatus.failure,
            "Changed status to failed",
            "Dist-git MR CI Pipeline",
            "https://gitlab.com/packit-as-a-service-stg/open-vm-tools/-/pipelines/497396723",
            id="Stream Gitlab pipeline",
        ),
    ],
)
def test_sync_from_dist_git(
    event,
    src_project_url,
    status_state,
    status_description,
    status_check_name,
    status_url,
    request,
):
    event = Parser.parse_event(request.getfixturevalue(event))
    handler = (
        SyncFromPagurePRHandler
        if isinstance(event, PullRequestFlagPagureEvent)
        else SyncFromGitlabMRHandler
    )

    dist_git_pr_model = flexmock(id=2)
    flexmock(handler).should_receive("dist_git_pr_model").and_return(dist_git_pr_model)

    source_git_pr = flexmock(id=123, head_commit="foobar")
    source_git_project = flexmock(
        project_url=src_project_url,
        get_pr=source_git_pr,
    )
    source_git_pr_model = flexmock(pr_id=123, project=source_git_project)
    source_git_pr_dist_git_pr_model = flexmock(
        source_git_pull_request=source_git_pr_model
    )
    flexmock(SourceGitPRDistGitPRModel).should_receive("get_by_dist_git_id").with_args(
        2
    ).and_return(source_git_pr_dist_git_pr_model)
    flexmock(ServiceConfig).should_receive("get_project").with_args(
        url=src_project_url
    ).and_return(source_git_project)

    status_reporter = flexmock()
    status_reporter.should_receive("set_status").with_args(
        state=status_state,
        description=status_description,
        check_name=status_check_name,
        url=status_url,
    )
    flexmock(StatusReporter).should_receive("get_instance").with_args(
        project=source_git_project, commit_sha="foobar", pr_id=123
    ).and_return(status_reporter)

    handler(
        package_config=None,
        event=event.get_dict(),
        job_config=None,
    ).run()
