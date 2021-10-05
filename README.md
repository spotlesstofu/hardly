# Hardly

Code for (Celery) worker used in our "Stream service".
It reuses [packit-service's worker](https://github.com/packit/packit-service/tree/main/packit_service/worker)
code and [implements new jobs as new handlers](https://github.com/packit/research/tree/main/split-the-stream#2-separate-workers).

## Workflow

The service is similar to [Packit service](https://github.com/packit/packit-service),
but is expected to eventually follow [this workflow](https://github.com/packit/research/tree/main/split-the-stream#what-does-the-source-git-workflow-mean):

##### Must have:

- [x] If a user creates a merge-request on the source-git repository:
  - [x] Create a matching merge-request to the dist-git repository.
  - [x] Sync the CI results from the dist-git merge-request to the source-git merge-request.
- [ ] If the dist-git is updated, update the source-git repository by opening a PR.
- [ ] User is able to convert source-git change to the dist-git change locally via CLI.

##### Should have:

- [ ] If the source-git merge-request is updated, update the dist-git merge-request.
- [ ] If the source-git merge-request is closed, close the dist-git merge-request.

##### Could have:

- [ ] User is able to re-trigger the dist-git CI from the source-git merge-request.
- [ ] User is able to re-create the dist-git MR from the source-git merge-request.

## Running it locally

[Similar to packit-service](https://github.com/packit/packit-service/blob/main/CONTRIBUTING.md#running-packit-service-locally)
we have a [docker-compose.yml](docker-compose.yml) for fast prototyping.
You might need to tweak it a bit (especially the volume mounts there) before running it,
because it expects that you have:

- secrets/stream/dev/ populated (linked) with secrets mostly taken from our internal repo.
  "Mostly", because you should use your credential where possible.
- ../ogr/, ../packit/ and ../packit-service/ dirs with the respected repos cloned.
  Those are mounted into the container so you don't have to rebuild the image each time you change anything in them.

Follow the [packit-service's guide](https://github.com/packit/packit-service/blob/main/CONTRIBUTING.md#running-packit-service-locally)
for the other settings. Once you have it running (and see no errors), you can test (uses [HTTPie](https://httpie.io)) the webhook with:

```
cat tests/data/webhooks/gitlab/mr_event.json | http --verify=no https://dev.packit.dev:8443/api/webhooks/gitlab
```

## How to deploy

To deploy the service into Openshift cluster,
clone the [deployment repo](https://github.com/packit/deployment) and:

1. [create the variable files](https://github.com/packit/deployment/tree/main/vars) in [vars/stream/](https://github.com/packit/deployment/tree/main/vars/stream)
2. link secrets into [secrets](https://github.com/packit/deployment/tree/main/secrets) / stream/{prod|stg}
3. `SERVICE=stream DEPLOYMENT={deployment} make deploy`

## Deployments

### Production

Production instance runs [here](https://console.pro-eu-west-1.openshift.com/console/project/stream-prod)
([API](https://prod.stream.packit.dev/api/)) and serves
[redhat/centos-stream/src/ repos](https://gitlab.com/redhat/centos-stream/src/).
Example:
[dist-git MR](https://gitlab.com/redhat/centos-stream/rpms/luksmeta/-/merge_requests/2)
created from
[source-git MR](https://gitlab.com/redhat/centos-stream/src/luksmeta/-/merge_requests/2).

### Staging

Staging instance runs [here](https://console.pro-eu-west-1.openshift.com/console/project/stream-stg)
([API](https://stg.stream.packit.dev/api/)) and is used to serve some
repos in our [packit-service/src/ namespace](https://gitlab.com/packit-service/src).
Because we can't use Group Webhooks there to set up the service for whole namespace
currently only some repos are served:

- open-vm-tools: [source-git MR](https://gitlab.com/packit-service/src/open-vm-tools/-/merge_requests/8) -> [dist-git MR](https://gitlab.com/packit-service/rpms/open-vm-tools/-/merge_requests/18)
- luksmeta: [source-git MR](https://gitlab.com/packit-service/src/luksmeta/-/merge_requests/2) -> [dist-git MR](https://gitlab.com/packit-service/rpms/luksmeta/-/merge_requests/2)

There are actually real staging src-git and dist-git repos in [redhat/centos-stream/staging namespace](https://gitlab.com/redhat/centos-stream/staging)
but we haven't used them yet, because the CI (Pipelines) there don't seem to work the same way as in prod repos
so we use repos in our namespace (see above) because we have at least full control over them.

#### CI @ staging

In order for us to be able to experiment with syncing CI results from a dist-git MR back to a source-git MR,
we have a fake CI setup.
There's a `.gitlab-ci.yml` stored in both, the source-git and dist-git repos served by the staging service.
In a source-git repo it's in `.distro/` ([example](https://gitlab.com/packit-service/src/open-vm-tools/-/blob/c9s/.distro/.gitlab-ci.yml))
and before the service creates a dist-git MR from a source-git MR the file is synced into the dist-git repo.
Once the dist-git MR is created the pipeline is run based on the file and the results are seen in the dist-git MR.
It's stored also in the dist-git repo ([example](https://gitlab.com/packit-service/rpms/open-vm-tools/-/blob/c9s/.gitlab-ci.yml)),
so that the file is not in a diff of a newly created dist-git MR as a newly added file.

### Syncing dist-git MR CI results back to a src-git MR

#### prod

The notification about a change of a pipeline's status is sent to a group webhook (with "Pipeline events" trigger)
which is manually added to the [redhat/centos-stream/rpms group](https://gitlab.com/redhat/centos-stream/rpms).

#### staging

For staging, a project webhook is added to forks in [packit-as-a-service-stg namespace](https://gitlab.com/packit-as-a-service-stg),
because that's where a pipeline runs in case of non-premium plan (packit-service/rpms/ namespace).

## Image

[The image](files/Containerfile) is currently based on the
[packit-worker image](https://github.com/packit/packit-service/blob/main/files/docker/Dockerfile.worker)
but that might change in the future to decouple those.

For running locally with docker-compose, build it with `docker-compose build`.

For deploying in cluster, the image is
[built and pushed](.github/workflows/rebuild-and-push-images.yml)
to [Quay.io](https://quay.io/repository/packit/hardly) whenever you push to `main`.
Or you can rebuild manually in
[Actions](https://github.com/packit/hardly/actions/workflows/rebuild-and-push-images.yml).

## Tests

Locally: `make test-image` && `make check-in-container`

CI: [Zuul](.zuul.yaml)
