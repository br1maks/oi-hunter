class MEXCAPIException(Exception):

    def __init__(self, message: str, status_code: int=None, response: dict=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)

class MEXCRateLimitException(MEXCAPIException):
    pass

class MEXCAuthException(MEXCAPIException):
    pass

class MEXCNotFoundException(MEXCAPIException):
    pass

class MEXCServerException(MEXCAPIException):
    pass

class MEXCNetworkException(MEXCAPIException):
    pass

class MEXCInvalidSymbolException(MEXCAPIException):
    pass