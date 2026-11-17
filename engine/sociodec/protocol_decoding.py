"""Strict protocol decoder."""
from __future__ import annotations
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

class ProtocolDecodeError(ValueError):
    pass
