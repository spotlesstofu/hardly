# Copyright Contributors to the Packit project.
# SPDX-License-Identifier: MIT

.PHONY: hardly test-image

BASE_IMAGE ?= quay.io/packit/packit-worker
# true|false
PULL_BASE_IMAGE ?= true
HARDLY_IMAGE ?= quay.io/packit/hardly:dev
TEST_IMAGE ?= hardly-tests
TEST_TARGET ?= ./tests/
CONTAINER_ENGINE ?= $(shell command -v podman 2> /dev/null || echo docker)
ANSIBLE_PYTHON ?= /usr/bin/python3
AP ?= ansible-playbook -vv -c local -i localhost, -e ansible_python_interpreter=$(ANSIBLE_PYTHON)
COV_REPORT ?= term-missing
COLOR ?= yes
SOURCE_BRANCH ?= $(shell git branch --show-current)

# The 'hardly' image is built FROM quay.io/packit/packit-worker
# which is pulled/updated before the build.
# If you want to build from your local worker image,
# i.e. don't want to pull the base image,
# set PULL_BASE_IMAGE=false
hardly: files/recipe-hardly.yaml files/install-deps.yaml
	$(CONTAINER_ENGINE) build --rm \
		--pull=$(PULL_BASE_IMAGE) \
		-t $(HARDLY_IMAGE) \
		-f files/Containerfile \
		--build-arg SOURCE_BRANCH=$(SOURCE_BRANCH) \
		.

check:
	find . -name "*.pyc" -exec rm {} \;
	PYTHONPATH=$(CURDIR) PYTHONDONTWRITEBYTECODE=1 python3 -m pytest --color=$(COLOR) --verbose --showlocals --cov=hardly --cov-report=$(COV_REPORT) $(TEST_TARGET)

test-image: files/recipe-tests.yaml
	$(CONTAINER_ENGINE) build --rm \
		-t $(TEST_IMAGE) \
		-f files/Containerfile.tests \
		--build-arg SOURCE_BRANCH=$(SOURCE_BRANCH) \
		.

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
