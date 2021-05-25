BASE_IMAGE ?= quay.io/packit/base
WORKER_IMAGE ?= quay.io/packit/hardly-worker:dev
TEST_IMAGE ?= quay.io/packit/hardly-worker-tests:stg
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
	PYTHONPATH=$(CURDIR) PYTHONDONTWRITEBYTECODE=1 python3 -m pytest --color=$(COLOR) --verbose --showlocals --cov=source_git_worker --cov-report=$(COV_REPORT) $(TEST_TARGET)

test_image: files/install-deps.yaml files/recipe-tests.yaml
	$(CONTAINER_ENGINE) build --rm -t $(TEST_IMAGE) -f files/docker/Dockerfile.tests --build-arg SOURCE_BRANCH=$(SOURCE_BRANCH) .

check_in_container:
	@# don't use -ti here in CI, TTY is not allocated in zuul
	echo $(SOURCE_BRANCH)
	$(CONTAINER_ENGINE) run --rm --pull=always \
		--env COV_REPORT \
		--env TEST_TARGET \
		--env COLOR \
		-v $(CURDIR):/src \
		-w /src \
		--security-opt label=disable \
		$(TEST_IMAGE) make check "TEST_TARGET=$(TEST_TARGET)"

check-inside-openshift-zuul:
	ANSIBLE_STDOUT_CALLBACK=debug $(AP) files/check-inside-openshift.yaml
