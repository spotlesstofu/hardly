# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

BASE_IMAGE ?= quay.io/packit/base
WORKER_IMAGE ?= quay.io/packit/hardly:dev
TEST_IMAGE ?= hardly-tests
TEST_TARGET ?= ./tests/unit ./tests/integration/
CONTAINER_ENGINE ?= $(shell command -v podman 2> /dev/null || echo docker)
ANSIBLE_PYTHON ?= /usr/bin/python3
AP ?= ansible-playbook -vv -c local -i localhost, -e ansible_python_interpreter=$(ANSIBLE_PYTHON)
COV_REPORT ?= term-missing
COLOR ?= yes
SOURCE_BRANCH ?= $(shell git branch --show-current)

worker: files/install-deps.yaml files/recipe-worker.yaml
	$(CONTAINER_ENGINE) pull $(BASE_IMAGE)
	$(CONTAINER_ENGINE) build --rm -t $(WORKER_IMAGE) -f files/docker/Dockerfile.worker --build-arg SOURCE_BRANCH=$(SOURCE_BRANCH) .

check:
	find . -name "*.pyc" -exec rm {} \;
	PYTHONPATH=$(CURDIR) PYTHONDONTWRITEBYTECODE=1 python3 -m pytest --color=$(COLOR) --verbose --showlocals --cov=hardly --cov-report=$(COV_REPORT) $(TEST_TARGET)

build-test-image: files/install-deps.yaml files/recipe-tests.yaml
	$(CONTAINER_ENGINE) build --rm -t $(TEST_IMAGE) -f files/docker/Dockerfile.tests --build-arg SOURCE_BRANCH=$(SOURCE_BRANCH) .

check-in-container:
	@# don't use -ti here in CI, TTY is not allocated in zuul
	echo $(SOURCE_BRANCH)
	$(CONTAINER_ENGINE) run --rm \
		--env COV_REPORT \
		--env TEST_TARGET \
		--env COLOR \
		-v $(CURDIR):/src \
		-w /src \
		--security-opt label=disable \
		$(TEST_IMAGE) make check "TEST_TARGET=$(TEST_TARGET)"

check-inside-openshift-zuul:
	ANSIBLE_STDOUT_CALLBACK=debug $(AP) files/check-inside-openshift.yaml
