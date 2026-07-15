# Handwriting Tools

This directory contains isolated tooling for handwriting assets used by the
injection workflow.

Generated images, masks, manifests, checkpoints, logs, and third-party source
belong under `DycomData/HandwritingAssets/` or another ignored local path. Do
not commit them.

The ScrabbleGAN subtool now has the host-side provider/cache contract used by
`--font-family handwriting` and the standalone
`uv run injection-pipeline generate-handwriting --seed <seed>` command. It
still keeps the legacy generator runtime outside the Python 3.13 environment.

The real Docker/upstream checkpoint path was verified locally on 2026-07-15
with the official Amazon source checkout, the IAM English options sidecar, and
the local `latest_net_G.pth` checkpoint. Missing checkpoint, options sidecar,
`.git_commit`/Git checkout metadata, or generator runtime is a hard error;
there is no fallback to a normal font renderer.
