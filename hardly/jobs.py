# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT
from logging import getLogger
from typing import List, Any

from hardly.handlers import DistGitPRHandler
from packit_service.worker.events import MergeRequestGitlabEvent
from packit_service.worker.handlers import JobHandler
from packit_service.worker.jobs import SteveJobs
from packit_service.worker.parser import CentosEventParser, Parser
from packit_service.worker.result import TaskResults

logger = getLogger(__name__)


class StreamJobs(SteveJobs):
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

        event_object: Any
        if source == "centosmsg":
            event_object = CentosEventParser().parse_event(event)
        else:
            event_object = Parser.parse_event(event)
        if not (event_object and event_object.pre_check()):
            return []

        # CoprBuildEvent.get_project returns None when the build id is not known
        if not event_object.project:
            logger.warning(
                "Cannot obtain project from this event! "
                "Skipping private repository check!"
            )
        elif event_object.project.is_private():
            service_with_namespace = (
                f"{event_object.project.service.hostname}/"
                f"{event_object.project.namespace}"
            )
            if (
                service_with_namespace
                not in self.service_config.enabled_private_namespaces
            ):
                logger.info(
                    f"We do not interact with private repositories by default. "
                    f"Add `{service_with_namespace}` to the `enabled_private_namespaces` "
                    f"in the service configuration."
                )
                return []
            logger.debug(
                f"Working in `{service_with_namespace}` namespace "
                f"which is private but enabled via configuration."
            )

        # DistGitPRHandler handler is (for now) run even the job is not configured in a package.
        if isinstance(event_object, MergeRequestGitlabEvent):
            DistGitPRHandler.get_signature(
                event=event_object,
                job=None,
            ).apply_async()
        processing_results = self.process_jobs(event_object)
        return processing_results
