"""Import a Colab fine-tuned checkpoint into the local models tree.

Phase Gamma kickoff — takes the zip Silviu downloads from
``MyDrive/hr_helper/checkpoints/<run_name>.zip`` and lays it out under
``nlp-service/models/skill_matcher/<run_name>/`` (gitignored per
``DECISIONS.md`` D4). Updates ``latest.txt`` atomically so future
scripts can pick the most recent checkpoint without an explicit
``--run-name`` flag.

CLI
---
Run from ``nlp-service/``::

    python scripts/import_finetuned_model.py \
      --zip <path-to-downloaded.zip> \
      --run-name mnrl_v1_20260520

The importer is **fail-loud and atomic**:

* All extraction happens inside a temp directory under
  ``models/skill_matcher/`` (same filesystem, so the final rename is
  atomic on POSIX and effectively atomic on NTFS).
* If any validation fails, the temp tree is cleaned up and **nothing**
  is left under the final ``<run_name>/`` path. A failed import never
  produces a half-imported checkpoint.
* ``latest.txt`` is written via temp + rename so a concurrent reader
  always sees either the previous run name or the new one — never a
  truncated file.

Validation steps
----------------
1. Zip readability.
2. Required artefacts present: ``<run_name>/<run_name>_manifest.json``
   and at least one of {``model.safetensors``, ``pytorch_model.bin``}.
3. Manifest is valid JSON and carries the locked fields
   (``base_model``, ``seed``, ``mode``, ``concept_text_format``).
4. Optional: the SentenceTransformer model loads end-to-end. Gated by
   ``--no-load-check`` because loading the real model takes ~3 s and
   needs the ``[ml]`` extra installed. The fast unit-test suite always
   sets ``--no-load-check`` to keep CI green without the heavy stack.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

# stdout reconfigure for Windows cp1252 console
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, OSError):
    pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

import structlog  # noqa: E402

logger = structlog.get_logger("import_finetuned_model")


_DEFAULT_MODELS_DIR = _REPO_ROOT / "models" / "skill_matcher"
_LATEST_FILE_NAME = "latest.txt"

# Manifest fields the importer requires. These are the "frozen" Step 5
# decisions — any divergence here is a sign the bundle did not match the
# notebook (e.g. the user ran a forked notebook variant).
_REQUIRED_MANIFEST_FIELDS = ("base_model", "seed", "mode", "concept_text_format")


class ImportError_(RuntimeError):
    """Raised when the import cannot proceed safely.

    Named ``ImportError_`` (trailing underscore) so it does not shadow
    the builtin :class:`ImportError`.
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_inner_dir(extracted_root: Path, run_name: str) -> Path:
    """Locate the inner ``<run_name>/`` directory the notebook produced.

    The training notebook zips with ``arcname=path.relative_to(root.parent)``
    so every entry is prefixed by ``<run_name>/``. After extraction, the
    contents live at ``<extracted_root>/<run_name>/...``.

    If the zip was repackaged without that prefix (e.g. Silviu unzipped +
    rezipped at the run-name level), fall back to treating
    ``extracted_root`` itself as the checkpoint dir — provided it carries
    the expected artefacts.
    """
    nested = extracted_root / run_name
    if nested.is_dir():
        return nested
    return extracted_root


def _validate_checkpoint_layout(checkpoint_dir: Path, run_name: str) -> Path:
    """Confirm the directory looks like a SentenceTransformer checkpoint.

    Returns the path to the run manifest on success.
    """
    if not checkpoint_dir.is_dir():
        raise ImportError_(
            f"Expected checkpoint directory {checkpoint_dir} after extraction."
        )

    manifest_path = checkpoint_dir / f"{run_name}_manifest.json"
    if not manifest_path.exists():
        # Fallback: some zips drop a generic manifest name.
        alt = list(checkpoint_dir.glob("*_manifest.json"))
        if not alt:
            raise ImportError_(
                f"Missing run manifest in {checkpoint_dir}. "
                f"Expected {manifest_path.name}."
            )
        manifest_path = alt[0]

    # Probe for the model weights — either safetensors or the legacy
    # pytorch_model.bin layout. SentenceTransformer keeps weights under
    # ``checkpoint_dir`` directly for v3+ models.
    weight_candidates = list(checkpoint_dir.rglob("model.safetensors")) + list(
        checkpoint_dir.rglob("pytorch_model.bin")
    )
    if not weight_candidates:
        raise ImportError_(
            f"No model weights found under {checkpoint_dir} "
            "(expected model.safetensors or pytorch_model.bin)."
        )

    return manifest_path


def _validate_manifest(manifest_path: Path) -> dict[str, Any]:
    """Parse + sanity-check the run manifest."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ImportError_(
            f"Run manifest is not valid JSON: {manifest_path}: {exc}"
        ) from exc

    missing = [f for f in _REQUIRED_MANIFEST_FIELDS if f not in manifest]
    if missing:
        raise ImportError_(
            f"Run manifest missing required fields {missing} at {manifest_path}."
        )

    if not isinstance(manifest, dict):  # defensive
        raise ImportError_(
            f"Run manifest must be a JSON object, got {type(manifest).__name__}."
        )
    return manifest


def _validate_model_loadable(checkpoint_dir: Path) -> None:
    """Load the checkpoint via :mod:`sentence_transformers` and run a probe.

    Imports sentence_transformers lazily so the unit-test suite (which
    sets ``--no-load-check``) does not pay for the import.
    """
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(str(checkpoint_dir))
    # Smoke test: encode three throwaway strings. Confirms the tokenizer,
    # encoder weights, and pooler all load and produce a sane shape.
    vec = model.encode(["one", "two", "three"], normalize_embeddings=True)
    if vec.shape[0] != 3:
        raise ImportError_(
            f"Encoded shape {vec.shape} does not match expected (3, *)."
        )
    logger.info(
        "import_finetuned_model.smoke_test_ok",
        encoded_shape=tuple(vec.shape),
    )


def _atomic_write_text(target: Path, text: str) -> None:
    """Write ``text`` to ``target`` atomically (temp + rename).

    Concurrent readers see either the previous file or the new one —
    never a truncated half-write.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(prefix=f"{target.name}.", dir=str(target.parent))
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(text)
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


# ---------------------------------------------------------------------------
# Top-level import
# ---------------------------------------------------------------------------


def import_finetuned_model(
    *,
    zip_path: Path,
    run_name: str,
    models_dir: Path = _DEFAULT_MODELS_DIR,
    load_check: bool = True,
) -> Path:
    """Import a Colab checkpoint zip into ``models_dir/<run_name>/``.

    Parameters
    ----------
    zip_path
        Path to the downloaded checkpoint zip.
    run_name
        Identifier used as the directory name and as the new contents of
        ``latest.txt``. Must match the run name baked into the manifest
        filename inside the zip (notebook convention).
    models_dir
        Override the default ``models/skill_matcher/`` parent. Tests use
        this to point at a tmp tree.
    load_check
        When ``True`` (CLI default), instantiate a real
        :class:`sentence_transformers.SentenceTransformer` against the
        extracted checkpoint. Disabled by unit tests via ``--no-load-check``
        so the fast suite does not need torch installed.

    Returns
    -------
    Path
        The final ``models_dir/<run_name>/`` directory.

    Raises
    ------
    FileNotFoundError
        If ``zip_path`` does not exist.
    ImportError_
        If the zip is unreadable, the layout is wrong, the manifest is
        missing/invalid, or the model fails to load (when enabled).
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"Checkpoint zip not found: {zip_path}")
    if not run_name or "/" in run_name or "\\" in run_name:
        raise ValueError(
            f"Invalid run_name {run_name!r}: must be non-empty and contain no path separators."
        )

    final_dir = models_dir / run_name
    if final_dir.exists():
        raise ImportError_(
            f"Refusing to overwrite existing checkpoint at {final_dir}. "
            "Delete it manually or choose a different --run-name."
        )

    models_dir.mkdir(parents=True, exist_ok=True)

    # Extract to a temp dir on the same filesystem (so the final rename
    # is atomic). ``shutil.move`` is used for the rename because it
    # tolerates both POSIX and NTFS semantics.
    staging = Path(
        tempfile.mkdtemp(prefix=f"import_{run_name}_", dir=str(models_dir))
    )
    try:
        try:
            with zipfile.ZipFile(zip_path) as zf:
                # Bail early on a truncated zip.
                if zf.testzip() is not None:
                    raise ImportError_(f"Zip {zip_path} has a corrupted entry.")
                zf.extractall(staging)
        except zipfile.BadZipFile as exc:
            raise ImportError_(f"Cannot read zip {zip_path}: {exc}") from exc

        checkpoint_dir = _find_inner_dir(staging, run_name)
        manifest_path = _validate_checkpoint_layout(checkpoint_dir, run_name)
        manifest = _validate_manifest(manifest_path)

        if load_check:
            _validate_model_loadable(checkpoint_dir)

        # Move into place. If the inner dir is nested under
        # ``staging/<run_name>``, we move the inner one; otherwise the
        # whole staging dir becomes the final dir.
        if checkpoint_dir == staging:
            shutil.move(str(staging), str(final_dir))
            staging = final_dir  # nothing left to clean up
        else:
            shutil.move(str(checkpoint_dir), str(final_dir))

        # Update latest.txt atomically.
        latest_path = models_dir / _LATEST_FILE_NAME
        _atomic_write_text(latest_path, run_name + "\n")

        logger.info(
            "import_finetuned_model.done",
            run_name=run_name,
            final_dir=str(final_dir),
            manifest=manifest,
            load_check=load_check,
        )
        return final_dir
    except Exception:
        # Best-effort cleanup of the staging directory. Never leave a
        # half-imported checkpoint lurking under models_dir.
        if staging.exists() and staging != final_dir:
            shutil.rmtree(staging, ignore_errors=True)
        if final_dir.exists():
            # Only happens if shutil.move partially succeeded — wipe.
            shutil.rmtree(final_dir, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a Colab fine-tuned checkpoint."
    )
    parser.add_argument(
        "--zip",
        dest="zip_path",
        type=Path,
        required=True,
        help="Path to the downloaded checkpoint zip.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        required=True,
        help=(
            "Run identifier; becomes models/skill_matcher/<run_name>/ "
            "and is written to latest.txt."
        ),
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=_DEFAULT_MODELS_DIR,
        help="Override the models/skill_matcher/ parent dir (mostly for tests).",
    )
    parser.add_argument(
        "--no-load-check",
        action="store_true",
        help=(
            "Skip the SentenceTransformer load test. Useful in CI where "
            "the ML extras are not installed."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    final_dir = import_finetuned_model(
        zip_path=args.zip_path,
        run_name=args.run_name,
        models_dir=args.models_dir,
        load_check=not args.no_load_check,
    )
    print(f"Imported checkpoint into: {final_dir}")
    print(f"latest.txt now points to: {args.run_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
