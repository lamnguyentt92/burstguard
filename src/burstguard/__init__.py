"""BurstGuard: robustness of federated fine-tuning of tiny time-series foundation models."""

__version__ = "0.3.4"
VERSION_TAG = f"v{__version__}"
DATA_FORMAT = 1  # bump when the processed .npz layout changes (file names carry this number)
# Version of the experiment code (models, attacks, defenses, metrics, grids). Releases that only change tooling keep
# it, so their results can be merged without a version-mix warning (0.3.0-0.3.3 share 0.3.0; 0.3.4 changed the
# defaults: 20 rounds, strong attacker, cheaper BurstGuard search).
EXPERIMENT_CODE = "0.3.4"
