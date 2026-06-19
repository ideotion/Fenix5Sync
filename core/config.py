"""Configuration loading for Fenix5Sync.

A single YAML file drives source path/mode, storage and DB locations, export
dir, server host/port, dedupe policy and log level. The core is usable with no
config file at all: :func:`load_config` falls back to built-in defaults so the
library works standalone. There are no hard-coded paths in the rest of the code
-- everything flows from :class:`Config`.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Search order for an existing config file when none is passed explicitly.
ENV_CONFIG_VAR = "FENIX5SYNC_CONFIG"
DEFAULT_CONFIG_PATHS = (
    "~/.config/fenix5sync/config.yaml",
    "./config.yaml",
)


def _expand(p: str) -> str:
    """Expand ``~`` and ``$ENV`` in a path string."""
    return os.path.expanduser(os.path.expandvars(p)) if p else p


@dataclass
class SourceConfig:
    mode: str = "auto"  # auto | mass_storage | mtp | path | folder | file | zip
    path: str = ""
    extra_mount_roots: list[str] = field(default_factory=list)
    activity_subdir: str = "GARMIN/Activity"
    mtp_mountpoint: str = "~/.cache/fenix5sync/mtp"
    recursive: bool = False  # descend into subdirectories (folder/zip/path dirs)
    formats: list[str] = field(default_factory=list)  # restrict to these; empty = all


@dataclass
class StorageConfig:
    data_dir: str = "~/.local/share/fenix5sync/data"
    raw_subdir: str = "raw"
    db_file: str = "~/.local/share/fenix5sync/data/fenix5sync.sqlite"

    @property
    def raw_dir(self) -> Path:
        return Path(_expand(self.data_dir)) / self.raw_subdir

    @property
    def db_path(self) -> Path:
        return Path(_expand(self.db_file))


@dataclass
class ExportConfig:
    output_dir: str = "~/.local/share/fenix5sync/exports"
    gpsbabel_bin: str = "gpsbabel"

    @property
    def output_path(self) -> Path:
        return Path(_expand(self.output_dir))


@dataclass
class DedupeConfig:
    enabled: bool = True


@dataclass
class AnonymizeConfig:
    """Optional, opt-in anonymization applied to a *copy* at export time.

    The stored archive is never modified. ``enabled`` is the master switch; an
    export may also force it on per-request. GPS scrubbing is off by default
    (you choose the level); device/personal stripping is on once you opt in.
    """

    enabled: bool = False
    drop_gps: bool = False           # remove all positions entirely
    privacy_radius_m: float = 0.0    # null positions within this radius of start & end
    fuzz_gps_m: float = 0.0          # jitter each remaining position by up to this many m
    strip_device: bool = True        # drop device make/model and serial/unit ids
    strip_personal: bool = True      # drop user-profile fields (age, weight, gender, ...)
    shift_dates: bool = False        # rebase timestamps to hide when you exercised


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True


@dataclass
class LoggingConfig:
    log_dir: str = "~/.local/share/fenix5sync/logs"
    level: str = "INFO"

    @property
    def log_path(self) -> Path:
        return Path(_expand(self.log_dir))


@dataclass
class Config:
    """Top-level configuration aggregate."""

    source: SourceConfig = field(default_factory=SourceConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    dedupe: DedupeConfig = field(default_factory=DedupeConfig)
    anonymize: AnonymizeConfig = field(default_factory=AnonymizeConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    # Absolute path this config was loaded from, if any (None = pure defaults).
    source_path: str | None = None

    # ---- (de)serialisation -------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Config":
        """Build a Config from a (partial) mapping, filling gaps with defaults."""
        data = data or {}

        def section(key: str, klass):
            raw = data.get(key) or {}
            if not isinstance(raw, dict):
                raise ValueError(f"config section '{key}' must be a mapping")
            known = {f for f in klass.__dataclass_fields__}
            unknown = set(raw) - known
            if unknown:
                raise ValueError(
                    f"unknown key(s) in config section '{key}': {sorted(unknown)}"
                )
            return klass(**raw)

        cfg = cls(
            source=section("source", SourceConfig),
            storage=section("storage", StorageConfig),
            export=section("export", ExportConfig),
            dedupe=section("dedupe", DedupeConfig),
            anonymize=section("anonymize", AnonymizeConfig),
            server=section("server", ServerConfig),
            logging=section("logging", LoggingConfig),
        )
        cfg.validate()
        return cfg

    def to_dict(self) -> dict[str, Any]:
        d = {k: asdict(v) for k, v in {
            "source": self.source,
            "storage": self.storage,
            "export": self.export,
            "dedupe": self.dedupe,
            "anonymize": self.anonymize,
            "server": self.server,
            "logging": self.logging,
        }.items()}
        return d

    def validate(self) -> None:
        """Reject obviously-wrong values early (with a clear message)."""
        valid_modes = {"auto", "mass_storage", "mtp", "path", "folder", "file", "zip"}
        if self.source.mode not in valid_modes:
            raise ValueError(
                "source.mode must be one of "
                f"{'|'.join(sorted(valid_modes))}, got {self.source.mode!r}"
            )
        if self.source.formats:
            from .importers import formats as _known_formats

            known = set(_known_formats())
            unknown = [f for f in self.source.formats if f not in known]
            if unknown:
                raise ValueError(
                    f"source.formats has unknown format(s): {sorted(unknown)}; "
                    f"known formats: {sorted(known)}"
                )
        # Security invariant: never bind to a non-loopback address by accident.
        if self.server.host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "server.host must be a loopback address (127.0.0.1/localhost/::1); "
                f"refusing {self.server.host!r} to keep the API local-only"
            )
        if not (0 < int(self.server.port) < 65536):
            raise ValueError(f"server.port out of range: {self.server.port}")
        if self.logging.level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ValueError(f"logging.level invalid: {self.logging.level}")
        if self.anonymize.privacy_radius_m < 0:
            raise ValueError("anonymize.privacy_radius_m must be >= 0")
        if self.anonymize.fuzz_gps_m < 0:
            raise ValueError("anonymize.fuzz_gps_m must be >= 0")


def find_config_path(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """Return the first existing config path, or None to use defaults."""
    candidates: list[str] = []
    if explicit:
        candidates.append(str(explicit))
    env = os.environ.get(ENV_CONFIG_VAR)
    if env:
        candidates.append(env)
    candidates.extend(DEFAULT_CONFIG_PATHS)
    for c in candidates:
        p = Path(_expand(c))
        if p.is_file():
            return p
    return None


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load configuration, falling back to defaults when no file is found.

    Args:
        path: explicit config file path. If None, the environment variable and
            the default search paths are consulted; absent all of those, the
            built-in defaults are returned.
    """
    cfg_path = find_config_path(path)
    if cfg_path is None:
        return Config()
    with cfg_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config file {cfg_path} must contain a YAML mapping")
    cfg = Config.from_dict(data)
    cfg.source_path = str(cfg_path)
    return cfg


def write_config(cfg: Config, path: str | os.PathLike[str]) -> Path:
    """Write a Config out as YAML, creating parent dirs. Returns the path."""
    p = Path(_expand(str(path)))
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg.to_dict(), fh, sort_keys=False, default_flow_style=False)
    return p
