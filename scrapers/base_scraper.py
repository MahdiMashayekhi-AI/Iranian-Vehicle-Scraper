from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseScraper(ABC):

  @abstractmethod
  def search(self, search_url: str, target_quota: int = 200) -> List[str]:
    raise NotImplementedError

  @abstractmethod
  def extract_listing(self, listing_url: str) -> Dict[str, Any]:
    raise NotImplementedError