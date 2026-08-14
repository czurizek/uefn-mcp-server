# Tools Reference

42 tools organized in 10 categories. Each tool maps 1:1 to a listener command.

---

## System

### `ping`

Check if the UEFN editor listener is running and responsive.

**Parameters:** none

**Response:**
```json
{
  "status": "ok",
  "python_version": "3.11.8 ...",
  "port": 8765,
  "timestamp": 1710892800.0,
  "commands": ["ping", "get_log", "execute_python", ...]
}
```

---

### `execute_python`

Execute arbitrary Python code inside the UEFN editor. This is the most powerful tool — it can do anything the `unreal` module supports.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `code` | string | yes | Python code to execute |

**Pre-populated globals:**

| Variable | Value |
|----------|-------|
| `unreal` | The `unreal` module |
| `actor_sub` | `unreal.get_editor_subsystem(unreal.EditorActorSubsystem)` |
| `asset_sub` | `unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)` |
| `level_sub` | `unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)` |
| `result` | Assign to this to return a value |

**Response fields:**

| Field | Description |
|-------|-------------|
| `result` | Value of the `result` variable after execution (JSON-serialized) |
| `stdout` | Captured `print()` output |
| `stderr` | Captured error output / tracebacks |

**Examples:**

```python
# Get the world name
result = unreal.EditorLevelLibrary.get_editor_world().get_name()
```

```python
# List all StaticMeshActor labels
actors = actor_sub.get_all_level_actors()
result = [a.get_actor_label() for a in actors if a.get_class().get_name() == 'StaticMeshActor']
```

```python
# Create a material
mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
    'M_Test', '/Game/Materials', unreal.Material, unreal.MaterialFactoryNew()
)
result = str(mat.get_path_name())
```

```python
# Batch rename selected assets with prefix
selected = unreal.EditorUtilityLibrary.get_selected_assets()
renamed = []
for asset in selected:
    name = asset.get_name()
    if not name.startswith('T_'):
        old_path = asset.get_path_name()
        folder = unreal.Paths.get_path(old_path)
        unreal.EditorAssetLibrary.rename_asset(old_path, folder + '/T_' + name)
        renamed.append(name)
result = {"renamed": renamed, "count": len(renamed)}
```

---

### `get_log`

Get recent MCP listener log entries.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `last_n` | int | no | 50 | Number of recent log lines to return |

**Response:**
```json
{
  "lines": [
    "[MCP] Listener started on http://127.0.0.1:8765",
    "[MCP] Registered 22 command handlers",
    ...
  ]
}
```

---

## Actors

### `get_all_actors`

List all actors in the current level.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `class_filter` | string | no | `""` | Filter by class name (e.g. `StaticMeshActor`, `PointLight`) |

**Response:**
```json
{
  "actors": [
    {
      "name": "StaticMeshActor_0",
      "label": "Cube",
      "class": "StaticMeshActor",
      "path": "/Game/Maps/TestLevel.TestLevel:PersistentLevel.StaticMeshActor_0",
      "location": {"x": 100.0, "y": 200.0, "z": 0.0},
      "rotation": {"pitch": 0.0, "yaw": 45.0, "roll": 0.0},
      "scale": {"x": 1.0, "y": 1.0, "z": 1.0}
    }
  ],
  "count": 1
}
```

---

### `get_selected_actors`

Get currently selected actors in the viewport.

**Parameters:** none

**Response:** Same format as `get_all_actors`.

---

### `spawn_actor`

Spawn an actor in the current level. Provide either `asset_path` OR `actor_class` (not both).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `asset_path` | string | no | `""` | Asset to spawn (e.g. `/Engine/BasicShapes/Cube`) |
| `actor_class` | string | no | `""` | UE class name (e.g. `PointLight`, `CameraActor`) |
| `location` | float[3] | no | `[0,0,0]` | World position `[x, y, z]` |
| `rotation` | float[3] | no | `[0,0,0]` | Rotation `[pitch, yaw, roll]` in degrees |

**Examples:**

Spawn a cube at position (500, 0, 100):
```json
{"asset_path": "/Engine/BasicShapes/Cube", "location": [500, 0, 100]}
```

Spawn a point light:
```json
{"actor_class": "PointLight", "location": [0, 0, 300]}
```

**Response:**
```json
{
  "actor": {
    "name": "StaticMeshActor_1",
    "label": "Cube",
    "class": "StaticMeshActor",
    "path": "...",
    "location": {"x": 500.0, "y": 0.0, "z": 100.0},
    "rotation": {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
    "scale": {"x": 1.0, "y": 1.0, "z": 1.0}
  }
}
```

---

### `delete_actors`

Delete actors by path name or label.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_paths` | string[] | yes | Actor path names or labels to delete |

**Response:**
```json
{
  "deleted": ["/Game/Maps/Level.Level:PersistentLevel.StaticMeshActor_0"],
  "count": 1
}
```

---

### `set_actor_transform`

Set an actor's location, rotation, and/or scale. Only provided fields are changed.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_path` | string | yes | Actor path name or label |
| `location` | float[3] | no | `[x, y, z]` world coordinates |
| `rotation` | float[3] | no | `[pitch, yaw, roll]` in degrees |
| `scale` | float[3] | no | `[x, y, z]` scale factors |

**Response:** The updated actor object (same format as `spawn_actor`).

---

### `get_actor_properties`

Read specific properties from an actor using `get_editor_property()`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_path` | string | yes | Actor path name or label |
| `properties` | string[] | yes | Property names to read |

**Response:**
```json
{
  "actor_path": "Cube",
  "properties": {
    "static_mesh_component": "/Game/Maps/Level...:StaticMeshComponent_0",
    "mobility": "EComponentMobility.STATIC"
  }
}
```

---

## Assets

### `list_assets`

List assets in a content directory.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `directory` | string | no | `/Game/` | Content path to list |
| `recursive` | bool | no | `true` | Include subdirectories |
| `class_filter` | string | no | `""` | Filter by class (e.g. `Material`, `StaticMesh`) |

**Response:**
```json
{
  "assets": [
    "/Game/Materials/M_Base",
    "/Game/Materials/M_Ground"
  ],
  "count": 2
}
```

---

### `get_asset_info`

Get detailed info about a specific asset.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `asset_path` | string | yes | Full asset path |

**Response:**
```json
{
  "asset": {
    "asset_name": "M_Base",
    "asset_class": "Material",
    "package_name": "/Game/Materials/M_Base",
    "package_path": "/Game/Materials",
    "object_path": "Material'/Game/Materials/M_Base.M_Base'"
  }
}
```

---

### `get_selected_assets`

Get assets currently selected in the Content Browser.

**Parameters:** none

**Response:**
```json
{
  "assets": ["/Game/Materials/M_Base", "/Game/Textures/T_Wood"],
  "count": 2
}
```

---

### `rename_asset`

Rename or move an asset.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `old_path` | string | yes | Current asset path |
| `new_path` | string | yes | New asset path |

**Response:**
```json
{
  "success": true,
  "old_path": "/Game/Materials/OldName",
  "new_path": "/Game/Materials/M_NewName"
}
```

---

### `delete_asset`

Delete an asset.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `asset_path` | string | yes | Asset path to delete |

**Response:**
```json
{"success": true, "asset_path": "/Game/Materials/M_Unused"}
```

---

### `duplicate_asset`

Duplicate an asset to a new path.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `source_path` | string | yes | Source asset path |
| `dest_path` | string | yes | Destination path |

**Response:**
```json
{
  "success": true,
  "source": "/Game/Materials/M_Base",
  "dest": "/Game/Materials/M_Base_Copy"
}
```

---

### `does_asset_exist`

Check if an asset exists.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `asset_path` | string | yes | Asset path to check |

**Response:**
```json
{"exists": true, "asset_path": "/Game/Materials/M_Base"}
```

---

### `save_asset`

Save a modified asset.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `asset_path` | string | yes | Asset path to save |

**Response:**
```json
{"success": true, "asset_path": "/Game/Materials/M_Base"}
```

---

### `search_assets`

Search for assets using the Asset Registry with class and path filters.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `class_name` | string | no | `""` | Class filter (e.g. `Material`, `Texture2D`) |
| `directory` | string | no | `/Game/` | Directory to search |
| `recursive` | bool | no | `true` | Include subdirectories |

**Response:**
```json
{
  "assets": [
    {"asset_name": "M_Base", "asset_class": "Material", ...},
    {"asset_name": "M_Ground", "asset_class": "Material", ...}
  ],
  "count": 2
}
```

---

## Level

### `save_current_level`

Save the current level.

**Parameters:** none

**Response:**
```json
{"success": true}
```

---

### `get_level_info`

Get basic info about the current level.

**Parameters:** none

**Response:**
```json
{
  "world_name": "TestLevel",
  "actor_count": 156
}
```

---

## Viewport

### `get_viewport_camera`

Get the current viewport camera position and rotation.

**Parameters:** none

**Response:**
```json
{
  "location": {"x": 500.0, "y": -200.0, "z": 300.0},
  "rotation": {"pitch": -30.0, "yaw": 45.0, "roll": 0.0}
}
```

---

### `set_viewport_camera`

Move the viewport camera. Only provided fields are changed.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `location` | float[3] | no | `[x, y, z]` world coordinates |
| `rotation` | float[3] | no | `[pitch, yaw, roll]` in degrees |

**Response:** The new camera position (same format as `get_viewport_camera`).

---

## New in v0.2.0

### `shutdown`

Gracefully stop the listener, freeing the port. The listener finishes the current request before shutting down.

**Parameters:** none

**Response:**
```json
{ "status": "shutting_down", "port": 8765 }
```

---

### `set_actor_properties`

Set properties on an actor via `set_editor_property()`.

> **Note:** UEFN uses Fort\*-prefixed actor classes. Not all properties are writable — some are read-only or don't exist on Fort\* actors. For methods like `set_actor_hidden_in_game()`, use `execute_python` instead.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_path` | string | yes | Actor path name or label |
| `properties` | object | yes | Dict of property names to values |

**Response:**
```json
{ "actor_path": "Cube", "properties": { "cast_shadow": "ok" } }
```

---

### `select_actors`

Programmatically select actors in the UEFN viewport.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_paths` | string[] | yes | List of actor path names or labels |
| `add_to_selection` | bool | no | Add to current selection instead of replacing (default: false) |

**Response:**
```json
{ "selected": ["Cube", "Cube2"], "count": 2 }
```

---

### `focus_selected`

Move the viewport camera to focus on the currently selected actors (like pressing F in the editor).

**Parameters:** none

**Response:**
```json
{ "center": { "x": 100, "y": 200, "z": 50 }, "camera": { "x": ..., "y": ..., "z": ... }, "actors_count": 2 }
```

---

### `get_editor_log`

Read recent lines from the Unreal Editor Output Log file (not the MCP log — the full editor log).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `last_n` | int | no | Number of recent lines (default: 100) |
| `filter_str` | string | no | Only lines containing this string (case-insensitive) |

**Response:** Newline-joined log lines.

---

### `get_project_info`

Get the UEFN project name and content root path. Use this to determine the correct base path for asset operations — in UEFN the content root is `/{ProjectName}/`, **not** `/Game/`.

**Parameters:** none

**Response:**
```json
{ "project_name": "MyProject", "content_root": "/MyProject/", "project_dir": "../../../FortniteGame/" }
```

---

## Geometry & Meshes

### `get_static_mesh_stats`

Read LOD, vertex, UV channel, collision, and Nanite stats for a StaticMesh asset.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `asset_path` | string | yes | Full asset path (e.g. `/Game/Meshes/SM_Rock`) |

**Response:**
```json
{
  "asset_path": "/Game/Meshes/SM_Rock",
  "lod_count": 4,
  "verts_per_lod": [1200, 640, 300, 120],
  "num_uv_channels": 1,
  "has_vertex_colors": false,
  "has_collision": true,
  "nanite_enabled": false
}
```

---

### `mesh_generate_lods`

Auto-generate simplified LODs for a StaticMesh. LOD0 stays full detail; each further LOD reduces triangle count by `base_percent_triangles` compounding (LOD1 ~= base, LOD2 ~= base^2, ...).

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `asset_path` | string | yes | — | Full asset path of the StaticMesh |
| `lod_count` | int | no | 4 | Total number of LODs, including LOD0 |
| `base_percent_triangles` | float | no | 0.5 | Triangle percentage kept per LOD step (0-1) |

**Response:**
```json
{ "asset_path": "/Game/Meshes/SM_Rock", "requested_lods": 4, "actual_lod_count": 4 }
```

---

### `mesh_add_collision`

Add simple collision to a StaticMesh.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `asset_path` | string | yes | — | Full asset path of the StaticMesh |
| `shape_type` | string | no | `Box` | One of Box, Sphere, Capsule, Convex, NDOP10, NDOP18, NDOP26 |

**Response:**
```json
{ "asset_path": "/Game/Meshes/SM_Rock", "shape_type": "Box" }
```

---

### `mesh_boolean`

Combine two StaticMeshes with a boolean operation (Union/Subtract/Intersection) into a new asset, created by duplicating `mesh_a_path` so material slots carry over.

> **Experimental:** relies on Geometry Script's Python bindings (`GeometryScript_AssetUtils`, `GeometryScript_MeshBooleanFunctions`), which can vary slightly across UEFN versions. If it errors, the traceback pinpoints exactly which struct or method needs adjusting — check the equivalent Blueprint nodes ("Apply Mesh Boolean" / "Copy Mesh From Static Mesh") for the current field names.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `mesh_a_path` | string | yes | — | First (target) StaticMesh asset path |
| `mesh_b_path` | string | yes | — | Second (tool) StaticMesh asset path |
| `output_path` | string | yes | — | Path for the new result asset |
| `operation` | string | no | `Union` | One of Union, Subtract, Intersection |

**Response:**
```json
{
  "output_path": "/Game/Meshes/SM_Combined",
  "operation": "Union",
  "source_a": "/Game/Meshes/SM_A",
  "source_b": "/Game/Meshes/SM_B"
}
```

---

## PCG (Procedural Content Generation)

Triggers/reads an actor's **existing** PCG graph — none of these tools author new PCG node graphs; that still has to be built once in-editor.

### `pcg_generate`

Trigger (re)generation of an actor's PCG graph.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `actor_path` | string | yes | — | Actor path name or label |
| `force` | bool | no | true | Force regeneration even if already generated |

**Response:**
```json
{ "actor_path": "PCG_Forest", "triggered": true }
```

---

### `pcg_cleanup`

Remove a PCG actor's generated output.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `actor_path` | string | yes | — | Actor path name or label |
| `remove_components` | bool | no | true | Also remove spawned component instances |

**Response:**
```json
{ "actor_path": "PCG_Forest", "cleaned": true }
```

---

### `pcg_get_status`

Read the state of an actor's PCGComponent.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_path` | string | yes | Actor path name or label |

**Response:**
```json
{ "actor_path": "PCG_Forest", "generated": true, "seed": 42, "graph": "/Game/PCG/PCG_ForestGraph" }
```

---

## Niagara VFX

### `niagara_spawn_effect`

Spawn a Niagara system into the level as a NiagaraActor.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `system_path` | string | yes | Asset path of the NiagaraSystem (e.g. `/Game/FX/NS_Fire`) |
| `location` | float[3] | no | `[x, y, z]` coordinates. Defaults to origin |
| `rotation` | float[3] | no | `[pitch, yaw, roll]` in degrees. Defaults to zero |

**Response:** Same shape as `spawn_actor`.

---

### `niagara_set_parameter`

Set a user parameter (float/vector/color/bool/int) on a spawned Niagara effect's component. Can only adjust parameters the effect's author already exposed as a User Parameter — cannot create effects or edit effect graphs.

> **Note:** parameter-setter method names changed across UE versions. This tool tries several known names (`set_variable_float`, `set_niagara_variable_float`, ...) and reports which one worked via `method_used`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_path` | string | yes | Actor path name or label of the spawned Niagara actor |
| `param_name` | string | yes | User parameter name as defined in the Niagara system |
| `param_type` | string | yes | One of float, vector, color, bool, int |
| `value` | any | yes | Number for float/int/bool, `[r,g,b,a]` for color, `[x,y,z]` for vector |

**Response:**
```json
{ "actor_path": "NiagaraActor_1", "param_name": "Color", "method_used": "set_variable_linear_color" }
```

---

### `niagara_set_active`

Activate or deactivate a spawned Niagara effect without destroying the actor.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `actor_path` | string | yes | — | Actor path name or label |
| `active` | bool | no | true | True to activate, false to deactivate |
| `reset` | bool | no | true | When activating, restart the effect from scratch |

**Response:**
```json
{ "actor_path": "NiagaraActor_1", "active": true }
```

---

### `niagara_get_info`

Read basic state of a spawned Niagara effect.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `actor_path` | string | yes | Actor path name or label |

**Response:**
```json
{ "actor_path": "NiagaraActor_1", "system_path": "/Game/FX/NS_Fire", "is_active": true, "seed": 0 }
```

---

## Project Health & Asset Validation

### `validate_asset_naming`

Check assets under a directory against prefix naming conventions. Ships with a default rule set (`StaticMesh`→`SM_`, `Material`→`M_`, `MaterialInstanceConstant`→`MI_`, `Texture2D`→`T_`, `Blueprint`→`BP_`, `NiagaraSystem`→`NS_`, and more) that `rules` can extend or override.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `directory` | string | no | `/Game/` | Content directory to scan |
| `rules` | object | no | — | `{class_name: expected_prefix}` overrides/additions |
| `recursive` | bool | no | true | Include subdirectories |

**Response:**
```json
{
  "checked": 84,
  "violations": [
    { "asset_path": "/Game/Meshes/Rock01", "asset_name": "Rock01", "asset_class": "StaticMesh", "expected_prefix": "SM_" }
  ],
  "violation_count": 1
}
```

---

### `find_unused_assets`

Find assets with no referencers in the project's asset database (candidates for cleanup).

> **Note:** only sees references tracked by the asset database — it cannot detect assets referenced solely from Verse code, so review results before deleting anything.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `directory` | string | no | `/Game/` | Content directory to scan |
| `recursive` | bool | no | true | Include subdirectories |

**Response:**
```json
{ "unused_assets": ["/Game/Materials/M_Old"], "count": 1, "scanned": 210 }
```

---

### `check_static_mesh_health`

Scan StaticMesh assets under a directory for missing collision and/or LODs.

**Parameters:**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `directory` | string | no | `/Game/` | Content directory to scan |
| `recursive` | bool | no | true | Include subdirectories |
| `require_collision` | bool | no | true | Flag meshes with no collision setup |
| `require_lods` | bool | no | true | Flag meshes with only a single LOD |

**Response:**
```json
{
  "checked": 40,
  "issues": [
    { "asset_path": "/Game/Meshes/SM_Rock", "problems": ["no_collision", "single_lod_only"] }
  ],
  "issue_count": 1
}
```
