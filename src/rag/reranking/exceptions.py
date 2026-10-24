class RerankerUnavailableError(RuntimeError):
    """Raised when the Voyage reranker is required but cannot be initialized or fails during a request."""
    pass

