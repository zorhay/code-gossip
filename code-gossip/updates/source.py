"""Prepare a validated release in temporary storage before running its installer."""

from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from . import github
from .config import DEFAULT_CONFIG, UpdateConfig, UpdatePaths
from .constants import REQUIRED_SOURCE_FILES, SOURCE_DIRECTORY_PREFIX, SOURCE_OWNER_FILE
from .entities import Release, UpdatePlan, UpdateProgress
from .errors import UpdateError
from .installation import run_installer
from .storage import installed_version, read_json, report_progress, write_json


def prepare_source(plan: UpdatePlan, progress: UpdateProgress) -> Path:
    work = create_workspace(plan.paths)
    progress.work = work
    report_progress(plan.paths, progress, "downloading", f"Downloading Code Gossip {plan.release.version}…")
    release = github.resolve_release(plan.release, plan.config)
    archive = github.download_release(release, work, plan.config)
    source = extract_archive(archive, work / "source", plan.config)
    validate_source(source, release)
    run_installer(source, plan.installation, plan.lock_fd, dry_run=True, config=plan.config)
    return source


def create_workspace(paths: UpdatePaths) -> Path:
    work = Path(tempfile.mkdtemp(prefix=SOURCE_DIRECTORY_PREFIX))
    write_json(work / SOURCE_OWNER_FILE, {"root": str(paths.root.resolve())})
    return work


def extract_archive(archive: Path, destination: Path, config: UpdateConfig = DEFAULT_CONFIG) -> Path:
    destination.mkdir()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > config.archive_member_limit or sum(m.file_size for m in members) > config.extracted_limit:
            raise UpdateError("Release archive is too large.")
        for member in members:
            extract_member(bundle, member, destination)
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise UpdateError("Release archive must contain one source directory.")
    return roots[0]


def extract_member(bundle: zipfile.ZipFile, member: zipfile.ZipInfo, destination: Path) -> None:
    relative = PurePosixPath(member.filename)
    if relative.is_absolute() or ".." in relative.parts or "\\" in member.filename or not relative.parts:
        raise UpdateError("Release archive contains an unsafe path.")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        # Only the repository's root convenience link can be omitted safely.
        if len(relative.parts) == 2 and relative.name == "uninstall.sh":
            return
        raise UpdateError("Release archive contains an unexpected symbolic link.")
    if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
        raise UpdateError("Release archive contains a special file.")
    target = destination.joinpath(*relative.parts)
    if member.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with bundle.open(member) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output)
        target.chmod(0o755 if mode & 0o111 else 0o644)


def validate_source(source: Path, release: Release) -> None:
    if any(not (source / name).is_file() for name in REQUIRED_SOURCE_FILES):
        raise UpdateError("Release is missing required installer/runtime files.")
    if installed_version(source / "code-gossip") != str(release.version):
        raise UpdateError("Release version does not match its source archive.")


def cleanup_source(paths: UpdatePaths, work: Path | None) -> None:
    if work is None:
        return
    # Never delete arbitrary paths read from an interrupted/corrupt state file.
    if (work.is_symlink() or not work.is_dir() or not work.name.startswith(SOURCE_DIRECTORY_PREFIX)
            or work.parent.resolve() != Path(tempfile.gettempdir()).resolve()):
        return
    try:
        owner = read_json(work / SOURCE_OWNER_FILE)
    except (OSError, ValueError):
        return
    if isinstance(owner, dict) and owner.get("root") == str(paths.root.resolve()):
        shutil.rmtree(work)


def cleanup_interrupted_sources(paths: UpdatePaths) -> None:
    # Includes a crash between creating a directory and recording its path.
    for work in Path(tempfile.gettempdir()).glob(SOURCE_DIRECTORY_PREFIX + "*"):
        cleanup_source(paths, work)
