#!/usr/bin/env python3
"""
Demo scenario for requirement #4: use the official Filesystem and Git MCP
servers together, driven by our manual MCP client.

Scenario (mirrors the PDF example):
    1. create a repository,
    2. create a README file inside it,
    3. add it to the repository,
    4. make a commit,
    5. show the git log.

NOTE / real-world finding: the current official `mcp-server-git` no longer
exposes a `git_init` tool (verified against the latest release). Repository
*creation* is therefore done with a plain `git init`; every other git action
(status, add, commit, log) goes through the official Git MCP server. Writing
files goes through the official Filesystem MCP server.

Run:  python src/demo_git_filesystem.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "host"))

import config  # noqa: E402
from chatbot import ChatSession  # noqa: E402


def show(title: str, result: dict) -> None:
    text = result.get("content", [{}])[0].get("text", "")
    flag = "ERROR" if result.get("isError") else "ok"
    print(f"\n=== {title} [{flag}] ===\n{text.strip()[:600]}")


def main() -> None:
    repo_dir = config.FILESYSTEM_ROOT / "farmavalle-project"
    repo_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: create the repository. (Official git server has no git_init.)
    subprocess.run(["git", "init", "-q", str(repo_dir)], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "demo@farmavalle.gt"], check=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "FarmaValle Bot"], check=True)
    print(f"Repository created at: {repo_dir}")

    session = ChatSession(enable_llm=False)
    status = session.connect_all(skip={"pharmacy"})
    print("Connected MCP servers:", status)

    try:
        # Step 2: create README via the Filesystem MCP server.
        show("filesystem.write_file README.md",
             session.call_tool_direct("filesystem", "write_file", {
                 "path": "farmavalle-project/README.md",
                 "content": "# FarmaValle Project\n\nCreated end-to-end through MCP servers.\n",
             }))

        # Step 3: stage it via the Git MCP server.
        show("git.git_add",
             session.call_tool_direct("git", "git_add", {
                 "repo_path": str(repo_dir), "files": ["README.md"]}))

        show("git.git_status",
             session.call_tool_direct("git", "git_status", {"repo_path": str(repo_dir)}))

        # Step 4: commit via the Git MCP server.
        show("git.git_commit",
             session.call_tool_direct("git", "git_commit", {
                 "repo_path": str(repo_dir), "message": "Add README (via MCP)"}))

        # Step 5: show the log via the Git MCP server.
        show("git.git_log",
             session.call_tool_direct("git", "git_log", {"repo_path": str(repo_dir)}))
    finally:
        session.close_all()

    print(f"\nDone. {len(session.logger.read_entries())} JSON-RPC messages logged to "
          f"{config.INTERACTION_LOG}")


if __name__ == "__main__":
    main()
