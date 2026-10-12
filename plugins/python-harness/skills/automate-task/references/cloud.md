<!-- Reference: Cloud and infrastructure automation with Python SDKs. Read when the user's request targets AWS, Google Cloud, or Azure automation. Researched 2026-10-06. -->

# Cloud / Infrastructure Automation

## Typical automations

- Provision, inspect, tag, update, or delete AWS resources through boto3 clients.
- Upload, download, copy, or synchronize S3 objects with bounded parallelism.
- Run asynchronous AWS API workflows with aioboto3.
- Transfer Google Cloud Storage objects using the storage client or transfer manager.
- Authenticate to Google Cloud through Application Default Credentials (ADC).
- Manage Azure resources with Azure Identity, Blob Storage, or `azure-mgmt-*` clients.
- Poll long-running cloud operations with SDK waiters or explicit status loops.
- Generate an execution plan, show changes, then apply only after confirmation.

## Package menu

| need                      | options                                                                                                         | choose when                                                                                                                                                                                                                                                                     | avoid when                                                                                                                                                                      | latest version                                                                                                                               | source                                                      |
| ------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| AWS SDK                   | **`boto3` rec**; `botocore` directly                                                                            | Use boto3 for service clients, resources, paginators, waiters, and S3 transfers. Use botocore directly only for lower-level integration. \[doc-verified: https://docs.aws.amazon.com/boto3/latest/guide/clients.html]                                                           | Do not use both layers without a reason; do not hard-code keys.                                                                                                                 | `boto3 1.43.108`; `botocore 1.43.108` \[doc-verified: https://pypi.org/pypi/boto3/json] \[doc-verified: https://pypi.org/pypi/botocore/json] | https://docs.aws.amazon.com/boto3/                          |
| AWS async API calls       | **`aioboto3` rec**; boto3 in threads                                                                            | Choose aioboto3 when the surrounding application is already asyncio-based and many independent API calls are I/O-bound. \[doc-verified: https://aioboto3.readthedocs.io/en/latest/]                                                                                             | Avoid adding async solely for a short sequential script.                                                                                                                        | `15.5.0` \[doc-verified: https://pypi.org/pypi/aioboto3/json]                                                                                | https://aioboto3.readthedocs.io/                            |
| AWS S3 file transfers     | **boto3 `TransferConfig` rec**; aioboto3                                                                        | `upload_file` and `download_file` support multipart transfers and configurable concurrency; `max_concurrency` defaults to 10 and threads can be disabled. \[doc-verified: https://docs.aws.amazon.com/boto3/latest/guide/s3.html#concurrent-transfer-operations]                | Do not independently fan out beyond service, network, or account limits.                                                                                                        | Included with `boto3 1.43.108` \[doc-verified: https://pypi.org/pypi/boto3/json]                                                             | https://docs.aws.amazon.com/boto3/latest/guide/s3.html      |
| Google Cloud Storage      | **`google-cloud-storage` rec**; stdlib HTTP only for exceptional cases                                          | Use the official client for buckets, blobs, retries, and transfer-manager operations. \[doc-verified: https://cloud.google.com/python/docs/reference/storage/latest]                                                                                                            | Avoid handwritten REST authentication and request signing.                                                                                                                      | `3.16.0` \[doc-verified: https://pypi.org/pypi/google-cloud-storage/json]                                                                    | https://cloud.google.com/storage/docs                       |
| Google authentication     | **`google-auth` rec**; explicit service-account credentials only when required                                  | Use ADC so the same script can use environment configuration, local `gcloud` ADC, or an attached service account. \[doc-verified: https://cloud.google.com/docs/authentication/application-default-credentials]                                                                 | Do not embed service-account keys; Google documents key files as a security risk. \[doc-verified: https://cloud.google.com/docs/authentication/application-default-credentials] | `2.60.0` \[doc-verified: https://pypi.org/pypi/google-auth/json]                                                                             | https://google-auth.readthedocs.io/                         |
| Azure identity            | **`azure-identity` rec**; explicit credential classes                                                           | Use `DefaultAzureCredential` for a configurable chain covering environment credentials, workload identity, managed identity, developer tools, and Azure CLI. \[doc-verified: https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential] | Avoid hard-coded client secrets or assuming one local login method works in production.                                                                                         | `1.26.0` \[doc-verified: https://pypi.org/pypi/azure-identity/json]                                                                          | https://learn.microsoft.com/en-us/python/api/azure-identity |
| Azure Blob Storage        | **`azure-storage-blob` rec**; async Azure Blob client when needed                                               | Use for containers, blobs, uploads, downloads, and blob service clients with `DefaultAzureCredential`. \[doc-verified: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-python-get-started]                                                                   | Avoid manually constructing authorization headers.                                                                                                                              | `12.31.0` \[doc-verified: https://pypi.org/pypi/azure-storage-blob/json]                                                                     | https://learn.microsoft.com/en-us/azure/storage/blobs/      |
| Azure resource management | **Relevant `azure-mgmt-*` package rec**; Azure CLI/IaC                                                          | Select the management-plane package matching the resource provider, such as `azure-mgmt-resource`; use it for explicit SDK workflows. \[doc-verified: https://learn.microsoft.com/en-us/python/api/azure-mgmt-resource/]                                                        | Avoid installing broad management packages unrelated to the requested resource.                                                                                                 | `azure-mgmt-resource 26.0.0` \[doc-verified: https://pypi.org/pypi/azure-mgmt-resource/json]                                                 | https://github.com/Azure/azure-sdk-for-python               |
| Zero-dependency utility   | **Python 3.12+ stdlib rec for glue**: `argparse`, `logging`, `json`, `pathlib`, `concurrent.futures`, `asyncio` | Choose when the script only orchestrates subprocesses, local files, or an already-installed CLI.                                                                                                                                                                                | Do not replace mature cloud SDK authentication and retry behavior with handwritten HTTP.                                                                                        | Python 3.12+ \[doc-verified: https://docs.python.org/3.12/]                                                                                  | https://docs.python.org/3.12/                               |

## Design choices to put to the user

01. **Authentication source:** environment/SSO/ADC/managed identity/Azure CLI versus an explicitly supplied credential object. Recommend environment, SSO, ADC, or managed identity because secrets must not be hard-coded.
02. **Plan and apply:** dry-run, plan-then-apply confirmation, or immediate mutation. Recommend plan-then-apply; where AWS supports it, pass the operation's `DryRun` parameter. \[doc-verified: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html]
03. **Idempotency:** create-if-missing, reconcile-to-desired-state, or one-shot action. Recommend reconcile-to-desired-state with stable names and tags.
04. **Scope:** account/project/subscription, region, resource IDs, and filters. Recommend explicit scope plus a required confirmation for destructive or broad operations.
05. **Tagging/labels:** required keys, values, and overwrite policy. Recommend applying owner, environment, purpose, and run identifier tags where the provider supports them.
06. **Failure policy:** fail-fast, continue and summarize, or rollback/compensate. Recommend continue for independent items, collect errors, and exit nonzero if any item failed.
07. **Retries and throttling:** SDK-managed retries versus application retries, with a maximum concurrency. Recommend SDK standard retries plus bounded application concurrency; Botocore supports `standard` and `adaptive` retry modes. \[doc-verified: https://docs.aws.amazon.com/sdkref/latest/guide/feature-retry-behavior.html]
08. **Output:** human-readable logs, JSON results, or both. Recommend logs on stderr and machine-readable JSON on stdout.
09. **Concurrency:** sequential, bounded threads, asyncio, or library-internal transfer parallelism. Recommend the smallest bounded level that meets the objective.
10. **IaC boundary:** script versus Terraform/IaC. Recommend Terraform when the desired state, drift detection, reviewable plans, and repeatable multi-resource lifecycle matter; consider the sibling `terraform-engineer` plugin.

## Concurrency profile

- Cloud API calls and object transfers are usually **I/O-bound**.
- Use `ThreadPoolExecutor` for synchronous boto3, Google, or Azure calls; use `asyncio` with aioboto3 or an async provider client when the complete workflow is asynchronous.
- Boto3 clients are generally thread-safe, while boto3 resources and sessions are not; do not share a session or resource across threads. Boto3 also cautions against creating `boto3.client()` through the shared default session concurrently. \[doc-verified: https://docs.aws.amazon.com/boto3/latest/guide/clients.html]
- A boto3 client uses a connection pool whose `max_pool_connections` default is 10; align worker count with the configured pool and service limits. \[doc-verified: https://docs.aws.amazon.com/botocore/latest/reference/config.html]
- S3 `TransferConfig.max_concurrency` defaults to 10 and uses threads unless `use_threads=False`. \[doc-verified: https://docs.aws.amazon.com/boto3/latest/guide/s3.html#concurrent-transfer-operations]
- Cap parallelism below the lowest of provider throttling limits, account quotas, connection-pool size, memory budget, and downstream service capacity.
- Prefer provider/library-internal transfer parallelism over nesting an outer executor around each multipart transfer.
- `ProcessPoolExecutor` is generally unsuitable for network-bound SDK calls; `InterpreterPoolExecutor` is unnecessary unless measured CPU-bound Python work exists.

## Pitfalls

- Hard-coded access keys, service-account keys, or client secrets — use environment configuration, SSO, ADC, workload identity, managed identity, or Azure CLI credentials.
- Creating one session/resource per item — create a controlled session/client lifecycle and avoid sharing non-thread-safe sessions/resources. \[doc-verified: https://docs.aws.amazon.com/boto3/latest/guide/clients.html]
- Assuming one API response contains every item — use service paginators where available. \[doc-verified: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/paginators.html]
- Busy-looping on asynchronous operations — use SDK waiters or bounded polling with timeout and backoff. \[doc-verified: https://docs.aws.amazon.com/boto3/latest/guide/clients.html]
- Treating retries as unlimited — configure total attempts, exponential backoff, and an overall deadline. \[doc-verified: https://docs.aws.amazon.com/botocore/latest/reference/config.html]
- Multiplying concurrency at several layers — choose one primary concurrency mechanism and cap it.
- Treating dry-run as universal — verify that the specific API supports an AWS `DryRun` parameter; otherwise implement a read-only plan followed by explicit apply.
- Deleting or overwriting without scope and confirmation — require explicit identifiers, tags, and a destructive-operation confirmation.
- Using a script for persistent desired state and drift management — use Terraform/IaC instead; the sibling `terraform-engineer` plugin is a better fit.

## Skeleton

```python
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from botocore.client import BaseClient

MANAGED_TAG = {'Key': 'managed-by', 'Value': 'automation'}


@dataclass(slots=True, kw_only=True, frozen=True)
class TagResult:
    resource_id: str
    applied: bool


def tag_resource(client: BaseClient, resource_id: str, *, dry_run: bool) -> TagResult:
    if not dry_run:
        client.create_tags(Resources=[resource_id], Tags=[MANAGED_TAG])
    return TagResult(resource_id=resource_id, applied=not dry_run)


def tag_resources(resource_ids: list[str], *, workers: int, dry_run: bool) -> list[TagResult]:
    config = Config(
        retries={'mode': 'standard', 'total_max_attempts': 5}, max_pool_connections=workers
    )
    client = boto3.session.Session().client('ec2', config=config)
    tag_one = partial(tag_resource, client, dry_run=dry_run)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(tag_one, resource_ids))
```
