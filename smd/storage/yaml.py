from pathlib import Path
from typing import Any
import yaml

class YAMLParser:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict[str, Any]:
        with self.path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
        
    def write(self, data: dict[str, Any]):
        with self.path.open("w", encoding="utf-8") as f:
            f.write(yaml.dump(data))
