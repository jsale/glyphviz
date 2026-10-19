"""Tiny client for the blender-mcp addon socket (127.0.0.1:9876).

The MCP server (`uvx blender-mcp`) is only a wrapper around this protocol; this
lets scripts drive the same addon when the mcp__blender__ tools aren't loaded.

    python bl.py info                 # scene summary
    python bl.py run script.py        # execute a bpy script inside Blender
"""
import json
import socket
import sys


def call(cmd_type, params=None, host="127.0.0.1", port=9876, timeout=600):
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(json.dumps({"type": cmd_type, "params": params or {}}).encode("utf-8"))
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode("utf-8"))
            except ValueError:
                continue
    raise RuntimeError("connection closed before a full reply")


def run_code(code):
    return call("execute_code", {"code": code})


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "info":
        print(json.dumps(call("get_scene_info"), indent=2))
    elif len(sys.argv) >= 3 and sys.argv[1] == "run":
        with open(sys.argv[2], encoding="utf-8") as f:
            print(json.dumps(run_code(f.read()), indent=2))
    else:
        print(__doc__)
