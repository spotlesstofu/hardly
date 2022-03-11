# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

import logging
from os import getenv
from typing import List

from celery import Task

from hardly.handlers.abstract import TaskName
from hardly.handlers.distgit import DistGitMRHandler, PipelineHandler
from hardly.jobs import StreamJobs
from packit_service.celerizer import celery_app
from packit_service.constants import (
    DEFAULT_RETRY_LIMIT,
    DEFAULT_RETRY_BACKOFF,
    CELERY_DEFAULT_MAIN_TASK_NAME,
)
from packit_service.utils import load_job_config, load_package_config
from packit_service.worker.result import TaskResults


# Let a remote debugger (Visual Studio Code client)
# access this running instance.
import debugpy

# Allow other computers to attach to debugpy at this IP address and port.
debugpy.listen(("0.0.0.0", 5678))

# Uncomment the following lines if you want to
# pause the program until a remote debugger is attached

# print("Waiting for debugger attach")
# debugpy.wait_for_client()
# debugpy.breakpoint()


logger = logging.getLogger(__name__)

# debug logs of these are super-duper verbose
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("github").setLevel(logging.WARNING)
logging.getLogger("kubernetes").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
# info is just enough
# logging.getLogger("ogr").setLevel(logging.INFO)
# easier debugging
logging.getLogger("ogr").setLevel(logging.DEBUG)
logging.getLogger("packit").setLevel(logging.DEBUG)
logging.getLogger("sandcastle").setLevel(logging.DEBUG)


# Don't import this (or anything) from p_s.worker.tasks,
# it would create the task from their process_message()
class HandlerTaskWithRetry(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {
        "max_retries": int(getenv("CELERY_RETRY_LIMIT", DEFAULT_RETRY_LIMIT))
    }
    retry_backoff = int(getenv("CELERY_RETRY_BACKOFF", DEFAULT_RETRY_BACKOFF))


@celery_app.task(
    name=getenv("CELERY_MAIN_TASK_NAME") or CELERY_DEFAULT_MAIN_TASK_NAME, bind=True
)
def hardly_process(
    self, event: dict, topic: str = None, source: str = None
) -> List[TaskResults]:
    """
    Main celery task for processing messages.

    :param event: event data
    :param topic: event topic
    :param source: event source
    :return: dictionary containing task results
    """
    return StreamJobs().process_message(event=event, topic=topic, source=source)


@celery_app.task(name=TaskName.dist_git_pr, base=HandlerTaskWithRetry)
def run_dist_git_sync_handler(event: dict, package_config: dict, job_config: dict):
    handler = DistGitMRHandler(
        package_config=load_package_config(package_config),
        job_config=load_job_config(job_config),
        event=event,
    )
    return get_handlers_task_results(handler.run_job(), event)


@celery_app.task(name=TaskName.pipeline, base=HandlerTaskWithRetry)
def run_pipeline_handler(event: dict, package_config: dict, job_config: dict):
    handler = PipelineHandler(
        package_config=load_package_config(package_config),
        job_config=load_job_config(job_config),
        event=event,
    )
    return get_handlers_task_results(handler.run_job(), event)


def get_handlers_task_results(results: dict, event: dict) -> dict:
    # include original event to provide more info
    return {"job": results, "event": event}
