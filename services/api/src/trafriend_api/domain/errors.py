class TraFriendDomainError(Exception):
    """Base error for expected domain failures."""


class FinancialInputError(TraFriendDomainError):
    """A financial input violates the calculation invariants."""


class CalculationOutOfDomainError(TraFriendDomainError):
    """The single-day linear model would produce a non-positive price."""


class ResourceNotFoundError(TraFriendDomainError):
    """A requested mock resource is not present."""


class UnsupportedFeatureError(TraFriendDomainError):
    """The requested instrument does not support a feature."""


class ReferenceUnavailableError(TraFriendDomainError):
    """No reference set is eligible for an authoritative calculation."""


class AnchorVersionInactiveError(TraFriendDomainError):
    """The submitted Daily Close Anchor version is not active."""


class AnchorUnavailableError(TraFriendDomainError):
    """No complete current Daily Close Anchor is available."""


class OvernightSessionError(TraFriendDomainError):
    """A timestamp or trading date is not part of a valid overnight session."""


class MarketDataProviderError(Exception):
    """Base error for normalized external market-data failures."""


class ProviderAuthenticationError(MarketDataProviderError):
    """Provider credentials are absent, invalid, or lack an entitlement."""


class ProviderRateLimitError(MarketDataProviderError):
    """The provider rejected a request because its rate limit was reached."""


class ProviderUnavailableError(MarketDataProviderError):
    """The provider could not serve a usable response."""
