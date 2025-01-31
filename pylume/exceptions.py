class LumeError(Exception):
    """Base exception for all PyLume errors."""
    pass

class LumeServerError(LumeError):
    """Raised when there's an error with the PyLume server."""
    def __init__(self, message: str, status_code: int = None, response_text: str = None):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)

class LumeConnectionError(LumeError):
    """Raised when there's an error connecting to the PyLume server."""
    pass

class LumeTimeoutError(LumeError):
    """Raised when a request to the PyLume server times out."""
    pass

class LumeNotFoundError(LumeError):
    """Raised when a requested resource is not found."""
    pass

class LumeConfigError(LumeError):
    """Raised when there's an error with the configuration."""
    pass

class LumeVMError(LumeError):
    """Raised when there's an error with a VM operation."""
    pass

class LumeImageError(LumeError):
    """Raised when there's an error with an image operation."""
    pass 