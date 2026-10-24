"""Evaluation package. `drift` only needs numpy; `ragas_runner` pulls in
ragas/langchain/mlflow — import submodules explicitly rather than via
this __init__ to keep lightweight use cases (e.g. drift-only monitoring)
free of heavy dependencies."""
