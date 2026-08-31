from abc import ABC, abstractmethod

from app.models import RateObservation


class RateStore(ABC):
    @abstractmethod
    def append(self, rows: list[RateObservation]) -> int:
        raise NotImplementedError

    @abstractmethod
    def read_all(self) -> list[RateObservation]:
        raise NotImplementedError
