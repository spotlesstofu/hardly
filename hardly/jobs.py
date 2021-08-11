# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
from logging import getLogger
from typing import List

from hardly.handlers import DistGitMRHandler
from packit_service.worker.events import Event, MergeRequestGitlabEvent
from packit_service.worker.handlers import JobHandler
from packit_service.worker.jobs import SteveJobs
from packit_service.worker.parser import Parser
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


class StreamJobs(SteveJobs):
    def process_jobs(self, event: Event) -> List[TaskResults]:
        return []  # For now, don't process default jobs, i.e. copr-build & tests
        # return super().process_jobs(event)

    def process_message(
        self, event: dict, topic: str = None, source: str = None
    ) -> List[TaskResults]:
        """
        Entrypoint for message processing.

        :param event:  dict with webhook/fed-mes payload
        :param topic:  meant to be a topic provided by messaging subsystem (fedmsg, mqqt)
        :param source: source of message
        """
        if topic:
            # let's pre-filter messages: we don't need to get debug logs from processing
            # messages when we know beforehand that we are not interested in messages for such topic
            topics = [
                getattr(handler, "topic", None)
                for handler in JobHandler.get_all_subclasses()
            ]

            if topic not in topics:
                logger.debug(f"{topic} not in {topics}")
                return []

        event_object = Parser.parse_event(event)
        if not (event_object and event_object.pre_check()):
            return []

        # CoprBuildEvent.get_project returns None when the build id is not known
        if not event_object.project:
            logger.warning(
                "Cannot obtain project from this event! "
                "Skipping private repository check!"
            )

        # DistGitMRHandler handler is (for now) run even the job is not configured in a package.
        if isinstance(event_object, MergeRequestGitlabEvent):
            DistGitMRHandler.get_signature(
                event=event_object,
                job=None,
            ).apply_async()

        return self.process_jobs(event_object)
