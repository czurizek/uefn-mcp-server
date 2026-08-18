"""Install the WORLD CITY leaderboard Verse module into the open UEFN project.

Copies `verse/world_city/*.verse` into the project's Content directory and, once
Verse code has been built, places the leaderboard device in the current level.

Run inside the UEFN editor, either way round:

  Tools > Execute Python Script  ->  select this file

  # or through the MCP server's execute_python tool
  import sys; sys.path.insert(0, r"C:/path/to/uefn-mcp-server/tools")
  import install_world_city
  result = install_world_city.install(expect_project="Sp4nky")

Verse itself cannot be compiled from Python (UEFN exposes no Verse bridge), so
the middle step stays manual: after installing, hit Verse > Build Verse Code,
then call place_device() to drop the device into the level.
"""

import filecmp
import os
import shutil
from typing import Any, Dict, List, Optional, Sequence

try:
    import unreal
except ImportError:  # Lets the path helpers run outside the editor.
    unreal = None  # type: ignore[assignment]


VERSE_FILES = (
    "world_city_stats.verse",
    "world_city_leaderboard_device.verse",
    "world_city_cash_source_device.verse",
)

DEFAULT_SUBDIR = "world_city"
LEADERBOARD_DEVICE = "world_city_leaderboard_device"


# -- Paths -------------------------------------------------------------------


def _has_sources(directory: str) -> bool:
    return all(os.path.isfile(os.path.join(directory, name)) for name in VERSE_FILES)


def _candidate_source_dirs() -> List[str]:
    """Places worth looking for the .verse sources, best guess first."""
    candidates = [os.environ.get("WORLD_CITY_SOURCE")]

    here = globals().get("__file__")
    if here:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(here)))
        candidates.append(os.path.join(repo_root, "verse", "world_city"))

    cwd = os.getcwd()
    candidates.append(os.path.join(cwd, "verse", "world_city"))
    candidates.append(cwd)

    return [os.path.normpath(c) for c in candidates if c]


def find_source_dir(explicit: Optional[str] = None) -> str:
    """Locate the folder holding the WORLD CITY .verse files."""
    if explicit:
        explicit = os.path.normpath(explicit)
        if _has_sources(explicit):
            return explicit
        raise FileNotFoundError(
            f"{explicit} does not hold the WORLD CITY sources ({', '.join(VERSE_FILES)})."
        )

    tried = _candidate_source_dirs()
    for candidate in tried:
        if _has_sources(candidate):
            return candidate
    raise FileNotFoundError(
        "Could not find the WORLD CITY .verse sources. Pass source_dir= or set "
        "WORLD_CITY_SOURCE to the repo's verse/world_city folder. Tried: "
        + ", ".join(tried)
    )


def _require_editor() -> None:
    if unreal is None:
        raise RuntimeError(
            "This script must run inside the UEFN editor (Tools > Execute Python "
            "Script, or the MCP execute_python tool)."
        )


def project_content_dir() -> str:
    """Absolute path of the open project's Content directory."""
    _require_editor()
    return os.path.normpath(str(unreal.Paths.project_content_dir()))


def project_name() -> str:
    """Name of the open project, e.g. "Sp4nky"."""
    _require_editor()
    project_file = str(unreal.Paths.get_project_file_path() or "")
    if project_file:
        return os.path.splitext(os.path.basename(project_file))[0]
    return os.path.basename(os.path.normpath(str(unreal.Paths.project_dir())))


# -- Install -----------------------------------------------------------------


def install(
    source_dir: Optional[str] = None,
    subdir: str = DEFAULT_SUBDIR,
    expect_project: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Copy the Verse module into `<project>/Content/<subdir>/`.

    Args:
        source_dir: Folder holding the .verse files. Auto-detected when omitted.
        subdir: Destination folder under Content. All files must stay together,
            they form one Verse module.
        expect_project: Refuse to install unless the open project has this name.
        force: Overwrite destination files that differ from the sources.

    Returns:
        Dict with the resolved paths plus per-file `copied` / `skipped` lists.
    """
    src = find_source_dir(source_dir)
    name = project_name()

    if expect_project and expect_project.strip().lower() != name.lower():
        raise RuntimeError(
            f"Open project is {name!r}, not {expect_project!r}. Open the right "
            "project, or drop expect_project to install into this one."
        )

    target = os.path.join(project_content_dir(), *subdir.split("/"))
    os.makedirs(target, exist_ok=True)

    copied: List[str] = []
    skipped: List[Dict[str, str]] = []
    for file_name in VERSE_FILES:
        source_path = os.path.join(src, file_name)
        target_path = os.path.join(target, file_name)

        if os.path.exists(target_path) and not force:
            if filecmp.cmp(source_path, target_path, shallow=False):
                skipped.append({"file": file_name, "reason": "already up to date"})
            else:
                skipped.append(
                    {"file": file_name, "reason": "local copy differs, pass force=True to overwrite"}
                )
            continue

        shutil.copyfile(source_path, target_path)
        copied.append(file_name)

    return {
        "project": name,
        "source_dir": src,
        "target_dir": target,
        "copied": copied,
        "skipped": skipped,
        "next_step": "Verse > Build Verse Code, then install_world_city.place_device()",
    }


# -- Place the device --------------------------------------------------------


def _content_roots(name: str) -> List[str]:
    """Mount points a UEFN project's Content can appear under."""
    return [f"/{name}/", "/Game/"]


def find_device_asset(
    subdir: str = DEFAULT_SUBDIR, asset_name: str = LEADERBOARD_DEVICE
) -> Optional[str]:
    """Package path of the asset generated for a Verse device, if it exists yet."""
    _require_editor()
    name = project_name()

    for root in _content_roots(name):
        direct = f"{root}{subdir}/{asset_name}"
        if unreal.EditorAssetLibrary.does_asset_exist(direct):
            return direct

    # The generated asset does not always land next to the .verse file.
    for root in _content_roots(name):
        if not unreal.EditorAssetLibrary.does_directory_exist(root):
            continue
        for asset_path in unreal.EditorAssetLibrary.list_assets(root, recursive=True):
            path = str(asset_path).split(".")[0]
            if path.rsplit("/", 1)[-1] == asset_name:
                return path
    return None


def _existing_instances(asset_name: str) -> List[str]:
    """Labels of actors in the level that are already this device."""
    actor_sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    found = []
    for actor in actor_sub.get_all_level_actors():
        try:
            class_name = actor.get_class().get_name()
        except Exception:
            continue
        if asset_name in class_name:
            found.append(actor.get_actor_label())
    return found


def place_device(
    subdir: str = DEFAULT_SUBDIR,
    asset_name: str = LEADERBOARD_DEVICE,
    location: Optional[Sequence[float]] = None,
    label: str = "WORLD_CITY_Leaderboard",
    force: bool = False,
) -> Dict[str, Any]:
    """Spawn the leaderboard device into the current level.

    The panel is drawn on the HUD, so the placement position does not matter.

    Args:
        subdir: Content folder the module was installed into.
        asset_name: Verse class to place.
        location: World position, defaults to the origin.
        label: Actor label to set, so the device is easy to find in the outliner.
        force: Place another instance even if one is already in the level.
    """
    _require_editor()

    asset_path = find_device_asset(subdir, asset_name)
    if asset_path is None:
        raise RuntimeError(
            f"No asset for {asset_name!r} yet. Run Verse > Build Verse Code in UEFN "
            "first - Python cannot compile Verse."
        )

    already = _existing_instances(asset_name)
    if already and not force:
        return {
            "placed": False,
            "reason": "already in the level",
            "existing": already,
            "asset_path": asset_path,
        }

    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if asset is None:
        raise RuntimeError(f"Failed to load asset: {asset_path}")

    position = unreal.Vector(*(location or (0.0, 0.0, 0.0)))
    actor = unreal.EditorLevelLibrary.spawn_actor_from_object(
        asset, position, unreal.Rotator(0.0, 0.0, 0.0)
    )
    if actor is None:
        raise RuntimeError(f"Failed to spawn {asset_path}")

    try:
        actor.set_actor_label(label)
    except Exception:
        pass

    return {
        "placed": True,
        "asset_path": asset_path,
        "actor": actor.get_actor_label(),
        "next_step": "Save the level, then launch a session to see the panel",
    }


# -- Script entry point ------------------------------------------------------


def main() -> Dict[str, Any]:
    """Install, then place the device if Verse code has already been built."""
    outcome = install()
    print(f"[world_city] project:   {outcome['project']}")
    print(f"[world_city] source:    {outcome['source_dir']}")
    print(f"[world_city] installed: {outcome['target_dir']}")
    for file_name in outcome["copied"]:
        print(f"[world_city]   copied  {file_name}")
    for entry in outcome["skipped"]:
        print(f"[world_city]   skipped {entry['file']} ({entry['reason']})")

    try:
        placement = place_device()
    except RuntimeError as exc:
        print(f"[world_city] {exc}")
        print("[world_city] then run: import install_world_city; install_world_city.place_device()")
        outcome["placed"] = False
        return outcome

    if placement.get("placed"):
        print(f"[world_city] placed {placement['actor']} from {placement['asset_path']}")
    else:
        print(f"[world_city] device {placement['reason']}: {placement.get('existing')}")
    outcome.update(placement)
    return outcome


if __name__ == "__main__":
    main()
