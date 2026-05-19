"""Source interface.

Every source (Greenhouse, Lever, a board aggregator, etc.) implements
`fetch()` and returns a list of JobListing objects. The pipeline doesn't
care where listings come from, only that they conform to this contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jobpipeline.models import JobListing


class JobSource(ABC):
    """Abstract base class for all job sources."""

    #: Short identifier stored on each listing, e.g. "greenhouse".
    name: str = "base"

    @abstractmethod
    def fetch(self) -> list[JobListing]:
        """Pull all current listings from this source.

        Implementations should be defensive: a single company's endpoint
        failing should not abort the whole fetch. Log and continue.
        """
        raise NotImplementedError
