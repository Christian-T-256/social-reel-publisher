"""Domain errors with messages that are safe to print in automation logs."""


class PublisherError(RuntimeError):
    """Base class for expected publisher failures."""


class ConfigurationError(PublisherError):
    """Required configuration is missing or invalid."""


class DestinationError(PublisherError):
    """A destination could not be proved safe."""


class MissingPinError(DestinationError):
    """No explicit destination pin exists for a platform."""


class DestinationMismatchError(DestinationError):
    """The credential resolves to an account other than the pinned account."""


class PostPublishMismatchError(DestinationError):
    """A created resource cannot be proved to have landed at the pinned account."""


class DeliveryError(PublisherError):
    """The API did not reach a documented successful terminal state."""
