from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PostResult:
    ok: bool
    detail: str   # uploader message or error text


class Uploader(ABC):
    """One video in, one PostResult out. Implementations must not raise for
    upload failures — that is what PostResult.ok=False is for."""

    @abstractmethod
    def upload(self, video_path: str, caption: str) -> PostResult: ...
