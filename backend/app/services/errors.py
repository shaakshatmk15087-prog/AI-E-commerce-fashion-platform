class ShopError(Exception):
    """Business-rule failure that maps to an HTTP error response."""

    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details
