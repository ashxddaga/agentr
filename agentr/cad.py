"""
agentr.cad: Native SolidCraft MCP evaluation, diagnostic probing,
            and multi-agent CAD verification benchmark.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
from typing import Dict, Any, List, Optional, Tuple


def find_solidcraft_cli() -> Optional[str]:
    """Find solidcraft-cli binary in path or local opt."""
    for path in [
        shutil.which("solidcraft-cli"),
        os.path.expanduser("~/.local/bin/solidcraft-cli"),
        os.path.expanduser("~/.local/opt/solidcraft/bin/solidcraft-cli"),
    ]:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


class SolidCraftMCPClient:
    """Minimal stdio MCP client for solidcraft-cli."""
    def __init__(self, cli_path: Optional[str] = None, allow_paths: Optional[List[str]] = None):
        self.cli = cli_path or find_solidcraft_cli()
        if not self.cli:
            raise RuntimeError("solidcraft-cli not found. Ensure SolidCraft is installed.")

        cmd = [self.cli, "mcp"]
        if allow_paths:
            for p in allow_paths:
                cmd.extend(["--allow-path", p])
        else:
            cmd.append("--allow-any-path")

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.req_id = 0
        self._init_mcp()

    def _init_mcp(self) -> None:
        self.rpc("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "agentr-cad", "version": "1.0"},
        })
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def send(self, msg: Dict[str, Any]) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.req_id += 1
        self.send({"jsonrpc": "2.0", "id": self.req_id, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                err = self.proc.stderr.read()
                raise RuntimeError(f"SolidCraft MCP closed stdout. stderr:\n{err}")
            msg = json.loads(line)
            if msg.get("id") == self.req_id:
                if "error" in msg:
                    raise RuntimeError(f"RPC error: {msg['error']}")
                return msg.get("result", {})

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return self.rpc("tools/call", {"name": name, "arguments": args})

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            if self.proc.stdout:
                self.proc.stdout.close()
            if self.proc.stderr:
                self.proc.stderr.close()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def parse_stl(filepath: str) -> Dict[str, Any]:
    """Parse binary STL to check watertightness (open edges) and calculate mesh volume."""
    with open(filepath, "rb") as f:
        data = f.read()
    if len(data) < 84:
        return {"error": "Invalid STL (too short)"}
    num_triangles = struct.unpack("<I", data[80:84])[0]
    if len(data) != 84 + num_triangles * 50:
        return {"error": f"size mismatch: {len(data)} vs {84 + num_triangles * 50}"}

    edges = {}
    total_vol = 0.0
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3

    for i in range(num_triangles):
        off = 84 + i * 50
        v = struct.unpack("<9f", data[off + 12:off + 48])
        tri = [v[0:3], v[3:6], v[6:9]]
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
        total_vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)) / 6.0
        for p in tri:
            for k in range(3):
                lo[k] = min(lo[k], p[k])
                hi[k] = max(hi[k], p[k])
        for a, b in ((0, 1), (1, 2), (2, 0)):
            e = tuple(sorted([tuple(round(x, 6) for x in tri[a]), tuple(round(x, 6) for x in tri[b])]))
            edges[e] = edges.get(e, 0) + 1

    open_edges = [e for e, c in edges.items() if c != 2]
    return {
        "triangles": num_triangles,
        "volume_mm3": round(abs(total_vol), 3),
        "bbox": {"min": [round(x, 3) for x in lo], "max": [round(x, 3) for x in hi]},
        "open_edges": len(open_edges),
        "watertight": (len(open_edges) == 0),
    }


def probe_solidcraft() -> Dict[str, Any]:
    """Inspect SolidCraft version, MCP tools, catalog count, and issue #8191 status."""
    cli = find_solidcraft_cli()
    if not cli:
        return {"error": "solidcraft-cli not found"}

    # Get version
    try:
        ver_proc = subprocess.run([cli, "--version"], capture_output=True, text=True, check=True)
        version_str = ver_proc.stdout.strip()
    except Exception as e:
        version_str = f"Error reading version: {e}"

    client = SolidCraftMCPClient(cli)
    try:
        # Tools count
        tools_res = client.rpc("tools/list", {})
        tools = [t["name"] for t in tools_res.get("tools", [])]

        # Catalog count
        cmds_res = client.call_tool("list_commands", {})
        cmds_txt = cmds_res.get("content", [{}])[0].get("text", "[]")
        try:
            catalog = json.loads(cmds_txt)
            catalog_count = len(catalog)
        except Exception:
            catalog_count = 0

        # Probe #8191 (Parameter expressions in sketch primitives)
        client.call_tool("new_design", {})
        client.call_tool("execute", {"command": "parameters.add", "params": {"name": "W", "expression": "40 mm"}})
        client.call_tool("execute", {"command": "sketch.create", "params": {"plane": "XY", "name": "S"}})

        # Baseline: sketch.line with expression points (should work)
        line_res = client.call_tool("execute", {"command": "sketch.line", "params": {"points": [[0, 0], ["W", 0]]}})
        line_ok = not line_res.get("isError", False)

        # Probe circle center with radius expression "W / 4"
        circle_res = client.call_tool("execute", {"command": "sketch.circle.center", "params": {"center": [0, 0], "radius": "W / 4"}})
        circle_ok = not circle_res.get("isError", False)

        # Probe rectangle with corner expression
        rect_res = client.call_tool("execute", {"command": "sketch.rectangle.two_point", "params": {"p0": [0, 0], "p1": ["W", 20]}})
        rect_ok = not rect_res.get("isError", False)

        # Probe ellipse with minor radius expression
        ellipse_res = client.call_tool("execute", {"command": "sketch.ellipse", "params": {"center": [0, 0], "major": ["W", 0], "minor_radius": "W / 4"}})
        ellipse_ok = not ellipse_res.get("isError", False)

        issue_8191_present = not (circle_ok and rect_ok and ellipse_ok)

        return {
            "version": version_str,
            "binary_path": cli,
            "mcp_tools_count": len(tools),
            "mcp_tools": tools,
            "engine_commands_count": catalog_count,
            "issue_8191": {
                "bug_present": issue_8191_present,
                "sketch_line_expression": line_ok,
                "sketch_circle_expression": circle_ok,
                "sketch_rect_expression": rect_ok,
                "sketch_ellipse_expression": ellipse_ok,
            }
        }
    finally:
        client.close()


def benchmark_mount_plate(out_dir: str = "/tmp/agentr-cad-bench") -> Dict[str, Any]:
    """Run standard parametric mount-plate benchmark through SolidCraft MCP."""
    os.makedirs(out_dir, exist_ok=True)
    step_path = os.path.join(out_dir, "mount-plate.step")
    stl_path = os.path.join(out_dir, "mount-plate.stl")
    sc_path = os.path.join(out_dir, "mount-plate.sc")

    t0 = time.time()
    client = SolidCraftMCPClient(allow_paths=[out_dir])
    try:
        client.call_tool("new_design", {})
        client.call_tool("execute", {"command": "parameters.change", "params": {"name": "width", "expression": "80 mm"}})
        client.call_tool("execute", {"command": "parameters.change", "params": {"name": "depth", "expression": "50 mm"}})
        client.call_tool("execute", {"command": "parameters.change", "params": {"name": "thick", "expression": "8 mm"}})

        client.call_tool("execute", {"command": "solid.box", "params": {"length": "width", "width": "depth", "height": "thick", "body_name": "Plate"}})
        client.call_tool("execute", {"command": "solid.fillet", "params": {"edges": [[0, 0, 4], [80, 0, 4], [80, 50, 4], [0, 50, 4]], "radius": "6 mm"}})
        for pos in [
            ["15 mm", "12 mm", "8 mm"],
            ["width - 15 mm", "12 mm", "8 mm"],
            ["15 mm", "depth - 12 mm", "8 mm"],
            ["width - 15 mm", "depth - 12 mm", "8 mm"],
        ]:
            client.call_tool("execute", {"command": "solid.hole", "params": {"position": pos, "clearance": "M4"}})

        # Measure 1: width 80
        m1 = json.loads(client.call_tool("measure", {})["content"][0]["text"])
        vol_80 = m1["bodies"][0]["volume_mm3"]

        # Parametric change: width -> 100
        client.call_tool("set_parameter", {"name": "width", "value": "100 mm"})

        # Measure 2: width 100
        m2 = json.loads(client.call_tool("measure", {})["content"][0]["text"])
        vol_100 = m2["bodies"][0]["volume_mm3"]

        # Exports
        client.call_tool("export", {"format": "step", "path": step_path})
        client.call_tool("export", {"format": "stl", "path": stl_path})
        client.call_tool("save", {"path": sc_path})

        duration = time.time() - t0

        # Hand calculations:
        # vol(w) = w*50*8 - 4*(36 - 9*pi)*8 - 4*pi*2.25^2*8
        def analytic_vol(w: float) -> float:
            return w * 50.0 * 8.0 - 4.0 * (36.0 - 9.0 * math.pi) * 8.0 - 4.0 * math.pi * (2.25 ** 2) * 8.0

        expected_80 = analytic_vol(80.0)
        expected_100 = analytic_vol(100.0)

        err_80 = abs(vol_80 - expected_80) / expected_80
        err_100 = abs(vol_100 - expected_100) / expected_100

        stl_info = parse_stl(stl_path) if os.path.exists(stl_path) else {"error": "STL export missing"}
        step_exists = os.path.exists(step_path)
        step_size = os.path.getsize(step_path) if step_exists else 0

        passed = (
            err_80 < 0.0001
            and err_100 < 0.0001
            and stl_info.get("watertight", False)
            and step_exists
        )

        return {
            "status": "PASS" if passed else "FAIL",
            "duration_s": round(duration, 3),
            "volume_80": {"measured": vol_80, "expected": round(expected_80, 3), "error_pct": round(err_80 * 100, 5)},
            "volume_100": {"measured": vol_100, "expected": round(expected_100, 3), "error_pct": round(err_100 * 5)},
            "step_export": {"size_bytes": step_size, "exists": step_exists},
            "stl_export": stl_info,
        }
    finally:
        client.close()


def run_cad_cli(args: List[str]) -> None:
    """Entrypoint for `agentr cad` CLI commands."""
    sub = args[0] if args else "probe"

    if sub in ("probe", "status"):
        print("\033[1;36m=== SolidCraft MCP Diagnostic Probe ===\033[0m")
        res = probe_solidcraft()
        if "error" in res:
            print(f"\033[31mError: {res['error']}\033[0m")
            sys.exit(1)

        print(f"• Version: \033[1m{res['version']}\033[0m ({res['binary_path']})")
        print(f"• MCP Tools: \033[32m{res['mcp_tools_count']} tools\033[0m")
        print(f"• Catalog Commands: \033[32m{res['engine_commands_count']} commands\033[0m")

        i8191 = res["issue_8191"]
        print("\n\033[1mUpstream Issue #8191 (Parameter expressions in sketch primitives):\033[0m")
        if i8191["bug_present"]:
            print("  ❌ \033[33mBug #8191 is PRESENT\033[0m (PR #8210 not yet integrated):")
            print(f"     - sketch.line with expression: {'✅ PASSED' if i8191['sketch_line_expression'] else '❌ FAILED'}")
            print(f"     - sketch.circle.center with expression radius: {'✅ PASSED' if i8191['sketch_circle_expression'] else '❌ FAILED'}")
            print(f"     - sketch.rectangle.two_point with expression corner: {'✅ PASSED' if i8191['sketch_rect_expression'] else '❌ FAILED'}")
            print(f"     - sketch.ellipse with expression radius: {'✅ PASSED' if i8191['sketch_ellipse_expression'] else '❌ FAILED'}")
        else:
            print("  ✅ \033[32mBug #8191 is RESOLVED\033[0m (all sketch primitives accept expressions).")

    elif sub in ("bench", "eval", "test"):
        print("\033[1;36m=== Running SolidCraft Parametric CAD Benchmark ===\033[0m")
        res = benchmark_mount_plate()
        status_color = "\033[32m" if res["status"] == "PASS" else "\033[31m"
        print(f"Status: {status_color}\033[1m{res['status']}\033[0m (took {res['duration_s']}s)")
        print(f"• Volume (w=80 mm):  {res['volume_80']['measured']} mm³ (expected {res['volume_80']['expected']})")
        print(f"• Volume (w=100 mm): {res['volume_100']['measured']} mm³ (expected {res['volume_100']['expected']})")
        print(f"• STEP Export: {res['step_export']['size_bytes']} bytes")
        stl = res["stl_export"]
        print(f"• STL Mesh: {stl.get('triangles')} triangles, Watertight: {'✅ YES' if stl.get('watertight') else '❌ NO'} ({stl.get('open_edges')} open edges)")

    elif sub in ("report", "markdown"):
        probe = probe_solidcraft()
        bench = benchmark_mount_plate()
        print(f"""# SolidCraft MCP Agent Evaluation Report
*Generated via `agentr cad` on {time.strftime('%Y-%m-%d %H:%M:%S')}*

## 1. System & Engine Overview
- **SolidCraft Version**: `{probe.get('version')}`
- **MCP Tools**: `{probe.get('mcp_tools_count')}`
- **Catalog Command Count**: `{probe.get('engine_commands_count')}`

## 2. Upstream Issue #8191 Status
- **Bug Present**: `{probe.get('issue_8191', {}).get('bug_present')}`
- `sketch.line` parameter expressions: `{probe.get('issue_8191', {}).get('sketch_line_expression')}`
- `sketch.circle.center` parameter expressions: `{probe.get('issue_8191', {}).get('sketch_circle_expression')}`
- `sketch.rectangle.*` parameter expressions: `{probe.get('issue_8191', {}).get('sketch_rect_expression')}`
- `sketch.ellipse` parameter expressions: `{probe.get('issue_8191', {}).get('sketch_ellipse_expression')}`

## 3. Parametric Benchmark (Mounting Plate)
- **Result**: **{bench.get('status')}** (completed in {bench.get('duration_s')}s)
- **Volume @ 80mm**: `{bench.get('volume_80', {}).get('measured')}` mm³ (Analytic: `{bench.get('volume_80', {}).get('expected')}`)
- **Volume @ 100mm**: `{bench.get('volume_100', {}).get('measured')}` mm³ (Analytic: `{bench.get('volume_100', {}).get('expected')}`)
- **STEP Export**: `{bench.get('step_export', {}).get('size_bytes')}` bytes
- **STL Mesh**: `{bench.get('stl_export', {}).get('triangles')}` triangles, Watertight: `{bench.get('stl_export', {}).get('watertight')}`
""")
    else:
        print("Usage: agentr cad [probe|bench|report]")
        sys.exit(1)
