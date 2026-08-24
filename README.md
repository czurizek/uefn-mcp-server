# UEFN MCP Server

Control [UEFN](https://dev.epicgames.com/documentation/en-us/fortnite/unreal-editor-for-fortnite) (Unreal Editor for Fortnite) from [Claude Code](https://docs.anthropic.com/en/docs/claude-code) via the [Model Context Protocol](https://modelcontextprotocol.io/).

```
Claude Code  <--stdio-->  MCP Server (mcp_server.py)  <--HTTP-->  Listener (uefn_listener.py, inside UEFN)
```

- **28 editor tools**: actors, assets, levels, viewport, project info, editor log, and arbitrary Python execution
- **14 island-analytics tools**: Discovery scoring, cohort benchmarks, movers (see [`fngg`](#island-analytics-fngg) below)
- **Zero C++ compilation** — pure Python, works across UEFN versions
- **Main-thread safe** — all `unreal.*` calls dispatched via editor tick callback

## Island Analytics (`fngg`)

Alongside the editor bridge, this repo ships **fngg** — a local app for browsing
Fortnite islands and analysing why they do or do not surface in Discover, with the
analytics tuned for **RP, FFA and open-world** maps.

```bash
python -m fngg demo     # sample data, so you can look around right now
python -m fngg serve    # dashboard at http://127.0.0.1:8770
```

Real data instead of samples:

```bash
python -m fngg sync --limit 2000   # pull Epic's public island catalogue
python -m fngg poll                # take one metric reading per island
python -m fngg watch               # keep polling — this is what builds history
```

- **Discovery Fitness** — a 0-100 score per island built on Epic's *documented*
  Discover inputs, broken into scale / retention / session depth / advocacy /
  momentum, each as a percentile against comparable islands. Comes with a ranked
  list of which weakness is actually worth fixing first.
- **Discover row fit** — the same measurements re-weighted per row (Popular,
  Trending, New Releases, By Players Like You, Community Choice, Top Charts), so
  you can see which tab your island is built for. Curated rows are reported as
  not-modelled, never scored.
- **Genre-aware cohorts** — an RP city with 90-minute sessions and a box-fight map
  with 4-minute sessions are never benchmarked against each other. Weights differ
  per genre: RP is retention-led, FFA is scale- and momentum-led.
- **Zero dependencies** — stdlib only. The dashboard is server-rendered with inline
  SVG charts; no CDN, works offline, light and dark.
- **14 more MCP tools** via `fngg_mcp_server.py`, so you can ask Claude Code
  *"how does my RP map compare to its cohort, and what should I fix first?"* in the
  same session where you are building it.

> Epic's Ecosystem API returns one live reading per metric and refuses data older
> than about six days — it never backfills. A day you did not poll is a day nobody
> can reconstruct, which is why fngg keeps its own append-only snapshot log.

Full guide: **[docs/fngg.md](docs/fngg.md)**

---

## Quick Start

### 0. Let Claude do the setup

Open Claude Code and ask: *"Help me set up UEFN MCP server"* — it will install dependencies, create config files, and walk you through the rest.

If you prefer to do it manually, follow steps 1-5 below.

### 1. Enable Python in UEFN

1. Open your project in UEFN
2. Go to **Project > Project Settings**
3. Search for **Python** and check the box for **Python Editor Script Plugin**

### 2. Start the listener inside UEFN

Use **Tools > Execute Python Script** in the UEFN menu bar, then select the `uefn_listener.py` file.

A **status window** will appear showing:
- **Listener status** — green when running, red when stopped
- **MCP Server status** — green when Claude Code is connected (heartbeat every 10s)
- **Port** — editable when listener is stopped
- **Metrics** — uptime, request count, errors, last command, avg response time
- **Controls** — Stop / Start / Restart buttons

You can safely close this window — the listener continues running in the background.

### 3. Install MCP SDK

On your system (not inside UEFN):

```bash
pip install mcp
```

### 4. Configure Claude Code

Create `.mcp.json` in your project root (or add to `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "uefn": {
      "command": "python",
      "args": ["C:/path/to/uefn-mcp-server/mcp_server.py"]
    }
  }
}
```

### 5. Restart Claude Code

Claude Code picks up `.mcp.json` on startup. After restart, you'll have 28 UEFN tools available.

### Try it

Ask Claude Code:
- *"List all actors in the level"*
- *"Spawn a cube at position 100, 200, 300"*
- *"What assets are in /Game/Materials/?"*
- *"Move the viewport camera to look at the origin"*

## Auto-start (optional)

To start the listener automatically when UEFN opens your project:

```bash
# Copy both files to your UEFN project's Content/Python/ directory
cp uefn_listener.py  <YourUEFNProject>/Content/Python/uefn_listener.py
cp init_unreal.py     <YourUEFNProject>/Content/Python/init_unreal.py
```

UEFN automatically executes `init_unreal.py` on project open.

## Tools

| Category | Tools |
|----------|-------|
| **System** | `ping`, `execute_python`, `get_log`, `get_editor_log`, `shutdown` |
| **Actors** | `get_all_actors`, `get_selected_actors`, `spawn_actor`, `delete_actors`, `set_actor_transform`, `get_actor_properties`, `set_actor_properties`, `select_actors`, `focus_selected` |
| **Assets** | `list_assets`, `get_asset_info`, `get_selected_assets`, `rename_asset`, `delete_asset`, `duplicate_asset`, `does_asset_exist`, `save_asset`, `search_assets` |
| **Project** | `get_project_info` |
| **Level** | `save_current_level`, `get_level_info` |
| **Viewport** | `get_viewport_camera`, `set_viewport_camera` |

The `execute_python` tool is the most powerful — it runs arbitrary Python code inside the editor with full access to the `unreal` module:

```python
# Pre-populated variables: unreal, actor_sub, asset_sub, level_sub, tk, get_tk_root
# Assign to `result` to return a value

actors = actor_sub.get_all_level_actors()
result = [a.get_actor_label() for a in actors]
```

> **Tkinter note:** When creating UI windows via `execute_python`, use `get_tk_root()` + `tk.Toplevel(root)`. Never call `tk.Tk()` — multiple instances crash the editor.

## Architecture

The system uses two independently running Python processes:

| Component | File | Runs in | Python | Dependencies |
|-----------|------|---------|--------|--------------|
| **Listener** | `uefn_listener.py` | UEFN editor process | 3.11+ (embedded) | stdlib only |
| **MCP Server** | `mcp_server.py` | External process | 3.10+ (system) | `mcp` SDK |

**Why two processes?**
- All `unreal.*` calls must happen on the editor's main thread (tick callback)
- The MCP SDK needs pip-installable packages that can't be added to UEFN's embedded Python
- Each component can restart independently

See [docs/architecture.md](docs/architecture.md) for details.

## Configuration

### Custom port

```json
{
  "mcpServers": {
    "uefn": {
      "command": "python",
      "args": ["path/to/mcp_server.py", "--port", "8766"]
    }
  }
}
```

Or via environment variable:

```json
{
  "mcpServers": {
    "uefn": {
      "command": "python",
      "args": ["path/to/mcp_server.py"],
      "env": { "UEFN_MCP_PORT": "8766" }
    }
  }
}
```

## Bonus Tools

Scripts that run inside the UEFN editor to introspect the Python API.
Run via **Tools > Execute Python Script** in the UEFN menu bar.

| Script | Description |
|--------|-------------|
| [`tools/dump_uefn_api.py`](tools/dump_uefn_api.py) | Dump all classes, enums, structs, functions to JSON |
| [`tools/generate_uefn_stub.py`](tools/generate_uefn_stub.py) | Generate `.pyi` type stub for IDE autocomplete (37K+ types) |
| [`tests/test_feasibility.py`](tests/test_feasibility.py) | Verify UEFN sandbox supports HTTP/threading for MCP |

## Documentation

| Document | Description |
|----------|-------------|
| [Setup Guide](docs/setup.md) | Detailed installation and configuration |
| [Tools Reference](docs/tools_reference.md) | All 28 tools with parameters, examples, and responses |
| [Architecture](docs/architecture.md) | How the two-component system works internally |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [UEFN Python Capabilities](docs/uefn_python_capabilities.md) | Full API capabilities map — 37K types across 30 domains |
| [Island Analytics (`fngg`)](docs/fngg.md) | Browsing and Discovery analytics for RP / FFA / open-world maps |

## Requirements

- UEFN editor with Python scripting enabled (Project Settings)
- Python 3.10+ on host system
- `pip install mcp`
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI

## License

MIT
