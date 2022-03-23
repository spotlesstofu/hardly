# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
from flexmock import flexmock

from hardly.tasks import run_dist_git_sync_handler
from packit.api import PackitAPI
from packit.config.job_config import JobConfigTriggerType
from packit.local_project import LocalProject
from packit.upstream import Upstream
from packit_service.config import ServiceConfig
from packit_service.constants import SANDCASTLE_WORK_DIR
from packit_service.service.db_triggers import AddPullRequestDbTrigger
from packit_service.utils import dump_package_config
from packit_service.worker.monitoring import Pushgateway
from packit_service.worker.parser import Parser
from tests.spellbook import first_dict_value


def test_dist_git_mr(mr_event):
    source_git_yaml = {
        "upstream_project_url": "https://github.com/vmware/open-vm-tools.git",
        "upstream_ref": "stable-11.3.0",
        "downstream_package_name": "open-vm-tools",
        "specfile_path": ".distro/open-vm-tools.spec",
        "patch_generation_ignore_paths": [".distro"],
        "patch_generation_patch_id_digits": 1,
        "sync_changelog": True,
        "synced_files": [
            {
                "src": ".distro/",
                "dest": ".",
                "delete": True,
                "filters": [
                    "protect .git*",
                    "protect sources",
                    "exclude source-git.yaml",
                    "exclude .gitignore",
                ],
            }
        ],
        "sources": [
            {
                "path": "open-vm-tools-11.3.0-18090558.tar.gz",
                "url": "https://sources.stream.centos.org/sources/rpms/open-vm-tools/...",
            }
        ],
    }
    version = "11.3.0"

    trigger = flexmock(
        job_config_trigger_type=JobConfigTriggerType.pull_request, id=123, pr_id=5
    )
    flexmock(AddPullRequestDbTrigger).should_receive("db_trigger").and_return(trigger)

    source_project = flexmock(
        namespace="jpopelka",
        repo="src-open-vm-tools",
        get_file_content=lambda path, ref: source_git_yaml,
        full_repo_name="jpopelka/src-open-vm-tools",
    )
    lp = flexmock(
        LocalProject, refresh_the_arguments=lambda: None, checkout_ref=lambda ref: None
    )
    lp.git_project = source_project
    flexmock(Upstream).should_receive("get_specfile_version").and_return(version)

    config = ServiceConfig()
    config.command_handler_work_dir = SANDCASTLE_WORK_DIR
    config.gitlab_mr_targets_handled = None
    flexmock(ServiceConfig).should_receive("get_service_config").and_return(config)
    flexmock(Pushgateway).should_receive("push").once().and_return()
    flexmock(PackitAPI).should_receive("sync_release").with_args(
        version=version,
        add_new_sources=False,
        title="Yet another testing MR",
        description="""DnD RpcV3: A corrupted packet received may result in an out of bounds (OOB)
memory access if the length of the message received is less than the size
of the expected packet header.

---
###### Info for package maintainer
This MR has been automatically created from
[this source-git MR](https://gitlab.com/packit-service/src/open-vm-tools/-/merge_requests/5).""",
        sync_default_files=False,
        local_pr_branch_suffix="src-5",
        mark_commit_origin=True,
    ).once()

    event = Parser.parse_event(mr_event)
    results = run_dist_git_sync_handler(
        package_config=dump_package_config(event.package_config),
        event=event.get_dict(),
        job_config=None,
    )

    assert first_dict_value(results["job"])["success"]
