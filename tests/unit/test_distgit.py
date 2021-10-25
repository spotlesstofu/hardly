# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import pytest

from flexmock import flexmock
from hardly.handlers.distgit import DistGitMRHandler


@pytest.mark.parametrize(
    "targets_handled, target_repo, target_branch, handled",
    [
        pytest.param(
            None, "redhat/centos-stream/src/make", "c9s", True, id="no config"
        ),
        pytest.param(
            [flexmock(repo=None, branch="c9s")],
            "redhat/centos-stream/src/make",
            "c8",
            False,
            id="only branch config, mismatch",
        ),
        pytest.param(
            [flexmock(repo="redhat/centos-stream/src/.+", branch="c9s")],
            "redhat/centos-stream/src/make",
            "c9s",
            True,
            id="branch and repo config",
        ),
        pytest.param(
            [
                flexmock(repo="redhat/centos-stream/src/.+", branch="c9s"),
                flexmock(repo="packit-service/src/.+", branch=None),
            ],
            "packit-service/src/make",
            "rawhide",
            True,
            id="multi config, match",
        ),
        pytest.param(
            [
                flexmock(repo="redhat/centos-stream/src/.+", branch="c9s"),
                flexmock(repo="packit-service/src/.+", branch=None),
            ],
            "packit-service/rpms/make",
            "rawhide",
            False,
            id="multi config, repo mismatch",
        ),
        pytest.param(
            [
                flexmock(repo="packit-service/src/.+", branch="(c9s|rawhide)"),
                flexmock(repo="redhat/centos-stream/src/.+", branch="c9s"),
            ],
            "packit-service/src/make",
            "test",
            False,
            id="multi config, branch mismatch",
        ),
    ],
)
def test_handle_target(targets_handled, target_repo, target_branch, handled):
    """Check if target repositories and branches are correctly told to be handled or not,
    according to the service configuration."""
    service_config = flexmock(gitlab_mr_targets_handled=targets_handled)
    mock_mr_handler = flexmock(
        service_config=service_config,
        target_repo=target_repo,
        target_repo_branch=target_branch,
    )
    assert DistGitMRHandler.handle_target(mock_mr_handler) == handled
