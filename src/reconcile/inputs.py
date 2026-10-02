"""Procedência das entradas: nome do arquivo e SHA-256 do conteúdo."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class InputFile:
    name: str  # só o nome; o caminho varia entre máquinas e quebraria o determinismo
    sha256: str


def fingerprint(path: Path) -> InputFile:
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    return InputFile(name=path.name, sha256=digest)
