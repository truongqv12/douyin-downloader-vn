from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class PipelineResult:
    status: str = "pending"
    stage: str = "pending"
    outputs: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "stage": self.stage,
            "outputs": dict(self.outputs),
            "error": self.error,
        }
