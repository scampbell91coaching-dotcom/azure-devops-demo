# GitOps promotion concurrency

The Flask, private-platform, and Lead Magnets workflows all publish immutable images and then commit their desired image reference to `main`. Their promotion steps use `scripts/gitops/promote_image.py`.

For every bounded push attempt the helper fetches `origin/main`, resets the disposable Actions checkout to that exact tree, and regenerates only the target's owned image field. It then creates a normal commit and pushes without force. If `main` advanced, the rejected push is retried from the new remote tree (at most five attempts). This preserves developer commits and other services' promotion commits. If the desired value is already on remote `main`, the operation succeeds without a commit.

Workflow concurrency groups also cancel superseded runs of the same deployment workflow. Cross-service workflows deliberately do not share one GitHub concurrency group: GitHub retains at most one pending run per group, so a shared group could discard a valid queued promotion. Cross-service contention is instead handled by the bounded replay above.

Limitations: sustained write traffic can exhaust five attempts and fail the promotion after the image has been published. Rerunning the workflow is safe. A newer run for the same service may supersede an older run; immutable images remain available for rollback by promoting the previous SHA through the normal controlled workflow.
