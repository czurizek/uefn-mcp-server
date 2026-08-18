"""Test the WORLD CITY installer without a UEFN editor.

The editor calls are faked, so this runs anywhere:

  python tests/test_install_world_city.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import install_world_city as installer  # noqa: E402


# ---------------------------------------------------------------------------
# Fake editor
# ---------------------------------------------------------------------------


class _FakePaths:
    def __init__(self, project_dir, project_name="Sp4nky"):
        self._project_dir = project_dir
        self._project_name = project_name

    def project_content_dir(self):
        return os.path.join(self._project_dir, "Content")

    def project_dir(self):
        return self._project_dir

    def get_project_file_path(self):
        return os.path.join(self._project_dir, f"{self._project_name}.uefnproject")


class _FakeAssetLibrary:
    """Behaves like a project whose Verse code has not been built yet."""

    @staticmethod
    def does_asset_exist(_path):
        return False

    @staticmethod
    def does_directory_exist(_path):
        return False

    @staticmethod
    def list_assets(_path, recursive=True):
        return []


class _FakeActor:
    def __init__(self, class_name, label):
        self._class_name = class_name
        self._label = label

    def get_class(self):
        return self

    def get_name(self):
        return self._class_name

    def get_actor_label(self):
        return self._label

    def set_actor_label(self, label):
        self._label = label


class _BuiltAssetLibrary:
    """Behaves like a project where Verse code has been built."""

    device_path = "/Sp4nky/world_city/world_city_leaderboard_device"

    @classmethod
    def does_asset_exist(cls, path):
        return path == cls.device_path

    @staticmethod
    def does_directory_exist(_path):
        return True

    @classmethod
    def list_assets(cls, _path, recursive=True):
        return [f"{cls.device_path}.world_city_leaderboard_device"]

    @classmethod
    def load_asset(cls, path):
        return f"asset:{path}" if path == cls.device_path else None


class _FakeActorSubsystem:
    def __init__(self, actors):
        self._actors = actors

    def get_all_level_actors(self):
        return list(self._actors)


class _FakeLevelLibrary:
    def __init__(self, spawned):
        self._spawned = spawned

    def spawn_actor_from_object(self, asset, _location, _rotation):
        actor = _FakeActor("world_city_leaderboard_device_C", str(asset))
        self._spawned.append(actor)
        return actor


class _FakeUnreal:
    def __init__(self, project_dir, project_name="Sp4nky", built=False, actors=None):
        self.Paths = _FakePaths(project_dir, project_name)
        self.EditorAssetLibrary = _BuiltAssetLibrary if built else _FakeAssetLibrary
        self.spawned = []
        self._actors = actors or []
        self.EditorLevelLibrary = _FakeLevelLibrary(self.spawned)
        self.EditorActorSubsystem = "EditorActorSubsystem"

    def get_editor_subsystem(self, _class):
        return _FakeActorSubsystem(self._actors)

    @staticmethod
    def Vector(x, y, z):
        return (x, y, z)

    @staticmethod
    def Rotator(pitch, yaw, roll):
        return (pitch, yaw, roll)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_finds_sources_in_repo():
    """The .verse folder is found from the installer's own location."""
    source_dir = installer.find_source_dir()
    for name in installer.VERSE_FILES:
        assert os.path.isfile(os.path.join(source_dir, name)), name
    return f"sources at {source_dir}"


def test_explicit_source_must_be_right():
    """A wrong source_dir fails loudly instead of falling back."""
    try:
        installer.find_source_dir(tempfile.gettempdir())
    except FileNotFoundError:
        return "bad source_dir rejected"
    raise AssertionError("expected FileNotFoundError")


def test_requires_editor():
    """Outside UEFN the script refuses to guess."""
    saved, installer.unreal = installer.unreal, None
    try:
        installer.install()
    except RuntimeError as exc:
        return str(exc).split(".")[0]
    finally:
        installer.unreal = saved
    raise AssertionError("expected RuntimeError")


def test_install_copies_module(project_dir):
    """A fresh install lands all three files under Content/world_city."""
    result = installer.install()
    assert result["project"] == "Sp4nky", result["project"]
    assert sorted(result["copied"]) == sorted(installer.VERSE_FILES), result["copied"]
    assert result["skipped"] == [], result["skipped"]

    target = os.path.join(project_dir, "Content", "world_city")
    for name in installer.VERSE_FILES:
        assert os.path.isfile(os.path.join(target, name)), name
    return f"3 files -> {target}"


def test_reinstall_is_a_noop():
    """Running twice reports the files as up to date instead of recopying."""
    result = installer.install()
    assert result["copied"] == [], result["copied"]
    reasons = {entry["reason"] for entry in result["skipped"]}
    assert reasons == {"already up to date"}, reasons
    return "second run copied nothing"


def test_local_edits_are_kept_unless_forced(project_dir):
    """A file edited inside the project survives, until force=True."""
    edited = os.path.join(project_dir, "Content", "world_city", installer.VERSE_FILES[0])
    with open(edited, "a", encoding="utf-8") as handle:
        handle.write("\n# local tweak\n")

    result = installer.install()
    assert result["copied"] == [], result["copied"]
    assert any("differs" in entry["reason"] for entry in result["skipped"]), result["skipped"]

    with open(edited, encoding="utf-8") as handle:
        assert "# local tweak" in handle.read()

    forced = installer.install(force=True)
    assert installer.VERSE_FILES[0] in forced["copied"], forced["copied"]
    with open(edited, encoding="utf-8") as handle:
        assert "# local tweak" not in handle.read()
    return "kept without force, overwritten with force"


def test_wrong_project_is_refused():
    """expect_project guards against installing into the wrong island."""
    try:
        installer.install(expect_project="SomeOtherMap")
    except RuntimeError as exc:
        assert "Sp4nky" in str(exc), str(exc)
        return "mismatched project refused"
    raise AssertionError("expected RuntimeError")


def test_place_device_needs_a_verse_build():
    """Without a built device asset, placement explains what to do."""
    try:
        installer.place_device()
    except RuntimeError as exc:
        assert "Build Verse Code" in str(exc), str(exc)
        return "asks for Verse > Build Verse Code"
    raise AssertionError("expected RuntimeError")


def test_place_device_spawns(project_dir):
    """With the asset built, the device is spawned and labelled."""
    saved = installer.unreal
    installer.unreal = _FakeUnreal(project_dir, built=True)
    try:
        result = installer.place_device()
        assert result["placed"] is True, result
        assert result["asset_path"] == _BuiltAssetLibrary.device_path, result
        assert result["actor"] == "WORLD_CITY_Leaderboard", result
        assert len(installer.unreal.spawned) == 1
    finally:
        installer.unreal = saved
    return "spawned and labelled"


def test_place_device_skips_duplicates(project_dir):
    """A device already in the level is left alone unless force=True."""
    saved = installer.unreal
    existing = _FakeActor("world_city_leaderboard_device_C", "WORLD_CITY_Leaderboard")
    installer.unreal = _FakeUnreal(project_dir, built=True, actors=[existing])
    try:
        result = installer.place_device()
        assert result["placed"] is False, result
        assert result["existing"] == ["WORLD_CITY_Leaderboard"], result
        assert installer.unreal.spawned == []

        forced = installer.place_device(force=True)
        assert forced["placed"] is True, forced
        assert len(installer.unreal.spawned) == 1
    finally:
        installer.unreal = saved
    return "duplicate skipped, force places a second one"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def main():
    project_dir = tempfile.mkdtemp(prefix="Sp4nky_")
    installer.unreal = _FakeUnreal(project_dir)

    cases = [
        ("finds sources in repo", test_finds_sources_in_repo, ()),
        ("explicit source must be right", test_explicit_source_must_be_right, ()),
        ("requires editor", test_requires_editor, ()),
        ("install copies module", test_install_copies_module, (project_dir,)),
        ("reinstall is a no-op", test_reinstall_is_a_noop, ()),
        ("local edits kept unless forced", test_local_edits_are_kept_unless_forced, (project_dir,)),
        ("wrong project refused", test_wrong_project_is_refused, ()),
        ("place_device needs a Verse build", test_place_device_needs_a_verse_build, ()),
        ("place_device spawns the device", test_place_device_spawns, (project_dir,)),
        ("place_device skips duplicates", test_place_device_skips_duplicates, (project_dir,)),
    ]

    failures = 0
    try:
        for label, func, args in cases:
            try:
                detail = func(*args)
                print(f"PASS  {label}: {detail}")
            except Exception as exc:  # noqa: BLE001 - report and keep going
                failures += 1
                print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
