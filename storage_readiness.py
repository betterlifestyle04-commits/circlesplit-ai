"""Check whether the sandbox SQLite file lives below a real mounted disk.

No env var is itself proof of persistence. This conservative check accepts
only an explicit, non-root, actual filesystem mount containing the DB path.
It is designed for the single-instance, paid Render persistent disk option.

A free Render web service without a disk is always ephemeral. A verified
mount is not a substitute for external backups or disaster recovery.
"""
import os
from pathlib import Path


def mounted_database(db_path, mount_path):
    """A verified mount must contain the DB file, not just be a folder name."""
    if not mount_path or not isinstance(mount_path, str):
        return False
    try:
        mount_value = Path(mount_path).expanduser()
        db_value = Path(db_path).expanduser()
        if not mount_value.is_absolute() or not db_value.is_absolute():
            return False
        mount = mount_value.resolve(strict=False)
        db = db_value.resolve(strict=False)
        # / is a mountpoint even on an ephemeral container: never trust it.
        if mount == Path("/") or mount == db or mount not in db.parents:
            return False
        if not mount.is_dir() or not os.path.ismount(str(mount)):
            return False
        return True
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def storage_readiness(db_path, environ=None):
    """Return a privacy-minimal operational status, never raw filesystem paths."""
    env = os.environ if environ is None else environ
    on_render = env.get("RENDER") == "true"
    hosted = on_render or env.get("CIRCLESPLIT_HOSTED") == "1"
    mounted = mounted_database(db_path, env.get("CIRCLESPLIT_PERSISTENT_MOUNT"))
    guarded = env.get("CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB") == "1"
    if mounted:
        mode = "mounted-sqlite"
        notice = ("Configured SQLite file is under a verified filesystem mount. "
                  "External backups and single-instance operation are still required.")
    elif hosted:
        mode = "ephemeral-sqlite"
        notice = ("This hosted SQLite database is not on a verified persistent disk. "
                  "It can reset after a restart or redeployment. Sandbox orders "
                  "recorded before a reset need external reconciliation.")
    else:
        mode = "local-sqlite-unverified"
        notice = ("Local SQLite persistence has not been independently verified. "
                  "Protect the file with normal device backups.")
    return {
        "storage": mode,
        "persistent_mount_verified": mounted,
        "checkout_requires_persistent_mount": guarded,
        "sandbox_checkout_allowed": not guarded or mounted,
        "notice": notice,
    }
