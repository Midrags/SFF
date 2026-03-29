
from abc import ABC, abstractmethod
from typing import Union

from sff.steam_client import SteamInfoProvider
from sff.structs import LuaParsedInfo


class AppInjectionManager(ABC):
    @abstractmethod
    def add_ids(
        self, data: Union[int, list[int], LuaParsedInfo], skip_check: bool = False
    ) -> None:
        pass
    
    @abstractmethod
    def dlc_check(self, provider: SteamInfoProvider, base_id: int) -> None:        
        pass