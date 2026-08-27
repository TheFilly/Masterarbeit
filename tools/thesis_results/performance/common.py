"""Gemeinsame Hilfsfunktionen für reproduzierbare Laufzeitmessungen."""

from __future__ import annotations

import csv
import importlib
import os
import platform
import sys
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class TimingResult:
    """Messwerte für einen abgeschlossenen Verarbeitungsschritt."""

    elapsed_seconds: float
    peak_memory_bytes: int


# Input: Eine Funktion ohne Argumente für Laufzeit- und Speichermessung.
# Output: TimingResult mit verstrichener Zeit und maximal beobachtetem Speicherbedarf.
# Die Funktion misst ausschließlich den übergebenen Verarbeitungsschritt und verändert
# keine fachlichen Pipeline-Daten.
def measure_call[T](action: Callable[[], T]) -> tuple[T, TimingResult]:
    start = time.perf_counter()
    result = action()
    elapsed_seconds = time.perf_counter() - start
    return result, TimingResult(elapsed_seconds, peak_memory_bytes())


# Input: Keine fachlichen Eingaben.
# Output: Maximaler Resident- beziehungsweise Working-Set-Speicher.
# Unter Windows wird die native Prozessmetrik verwendet; unter POSIX wird der
# ru_maxrss-Wert plattformgerecht in Bytes umgerechnet.
def peak_memory_bytes() -> int:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("page_fault_count", ctypes.c_ulong),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(ProcessMemoryCounters)
        current_process = ctypes.windll.kernel32.GetCurrentProcess
        current_process.restype = wintypes.HANDLE
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        success = get_process_memory_info(
            current_process(), ctypes.byref(counters), counters.cb
        )
        if not success:
            return 0
        return int(counters.peak_working_set_size)

    resource_module = cast(Any, importlib.import_module("resource"))
    usage = resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss
    if sys_platform_is_macos():
        return int(usage)
    return int(usage) * 1024


# Input: Keine fachlichen Eingaben.
# Output: True auf macOS, sonst False.
# Die Hilfsfunktion hält die plattformabhängige ru_maxrss-Konvention an einer Stelle.
def sys_platform_is_macos() -> bool:
    return sys.platform == "darwin"


# Input: Eine beliebige Sequenz und positive Blockgröße.
# Output: Iterator über zusammenhängende Blöcke der Eingabesequenz.
# Die Funktion materialisiert keine zusätzlichen Kopien und weist ungültige
# Blockgrößen zurück.
def iter_blocks[T](items: Iterable[T], block_size: int) -> Iterator[list[T]]:
    if block_size < 1:
        raise ValueError("block_size muss mindestens 1 sein.")
    block: list[T] = []
    for item in items:
        block.append(item)
        if len(block) == block_size:
            yield block
            block = []
    if block:
        yield block


# Input: Zielpfad, Mapping mit Messwerten und erwartete Spaltenreihenfolge.
# Output: Keine Rückgabe; schreibt eine CSV-Datei einschließlich Kopfzeile.
# Vorhandene Dateien werden bewusst überschrieben, damit ein Benchmarklauf
# reproduzierbar aus einem definierten Ausgabeordner neu erzeugt werden kann.
def write_csv(
    path: Path,
    rows: Iterable[Mapping[str, object]],
    fieldnames: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# Input: Keine fachlichen Eingaben.
# Output: Reproduzierbarkeitsmetadaten der aktuellen Ausführungsumgebung.
# Die Werte beschreiben die Messumgebung ohne externe Dienste oder zusätzliche
# Abhängigkeiten.
def environment_metadata() -> dict[str, object]:
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
    }
