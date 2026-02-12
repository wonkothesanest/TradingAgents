"""Custom exceptions for the TradingAgents API."""


class APIException(Exception):
    """Base exception for all API errors."""

    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class JobNotFoundError(APIException):
    """Exception raised when a job ID does not exist."""

    def __init__(self, job_id: str):
        super().__init__(
            message=f"Job not found: {job_id}",
            status_code=404
        )
        self.job_id = job_id


class InvalidJobRequestError(APIException):
    """Exception raised when job request validation fails."""

    def __init__(self, message: str):
        super().__init__(
            message=f"Invalid job request: {message}",
            status_code=422
        )


class TradingAgentsExecutionError(APIException):
    """Exception raised when TradingAgentsGraph execution fails."""

    def __init__(self, ticker: str, date: str, error: str):
        super().__init__(
            message=f"TradingAgents analysis failed for {ticker} on {date}: {error}",
            status_code=500
        )
        self.ticker = ticker
        self.date = date
        self.original_error = error
