"""Local code execution engine used as a fallback when Judge0 is unavailable.

The engine runs submitted source code in a fresh subprocess and feeds each
test case's ``input`` value to the program's stdin, then compares the
program's stdout against the expected output. It supports the runtimes that
are installed on the host:

* Python     -> ``python`` (the interpreter running this backend)
* JavaScript -> ``node``
* C/C++      -> ``gcc`` / ``g++``
* Java       -> ``javac`` + ``java`` (a JDK must be installed)

C# and languages whose runtime is not installed report ``missing_runtime``
so the caller can surface a clear message instead of a misleading failure.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

EXEC_TIMEOUT_SECONDS = 5.0
MAX_CAPTURE_BYTES = 64 * 1024


async def execute_judge0(
    language: str,
    source: str,
    stdin_data: str = "",
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute code using the Judge0 API service (https://judge.bhasantar.com/judge0/)."""
    lang_key = (language or "").lower().strip()
    lang_id = settings.judge0_language_ids.get(lang_key)
    if not lang_id:
        return {
            "ok": False,
            "missing_runtime": False,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "error": f"Language '{language}' is not supported by Judge0.",
        }

    url = f"{settings.judge0_url.rstrip('/')}/submissions?base64_encoded=false&wait=true"
    payload = {
        "language_id": lang_id,
        "source_code": source,
        "stdin": stdin_data,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=timeout)
            if resp.status_code not in (200, 201):
                return {
                    "ok": False,
                    "missing_runtime": False,
                    "timed_out": False,
                    "stdout": "",
                    "stderr": f"Judge0 error (HTTP {resp.status_code})",
                    "error": f"Judge0 API returned HTTP status {resp.status_code}",
                }
            data = resp.json()
            stdout = data.get("stdout") or ""
            stderr = data.get("stderr") or ""
            compile_output = data.get("compile_output") or ""
            message = data.get("message") or ""
            status = data.get("status") or {}
            status_id = status.get("id")

            timed_out = status_id == 5
            combined_err = stderr or compile_output or message or ""

            return {
                "ok": True,
                "missing_runtime": False,
                "timed_out": timed_out,
                "stdout": stdout[:MAX_CAPTURE_BYTES],
                "stderr": combined_err[:MAX_CAPTURE_BYTES],
                "status_id": status_id,
                "status_description": status.get("description", ""),
                "time": data.get("time"),
                "memory": data.get("memory"),
                "error": "",
            }
    except Exception as exc:
        return {
            "ok": False,
            "missing_runtime": False,
            "timed_out": False,
            "stdout": "",
            "stderr": f"Judge0 connection failed: {exc}",
            "error": str(exc),
        }


async def execute_code(
    language: str,
    source: str,
    stdin_data: str = "",
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute code using Judge0 first, falling back to local sandboxed execution."""
    result = await execute_judge0(language, source, stdin_data, timeout)
    if result.get("ok"):
        return result

    local_result = await execute_local(language, source, stdin_data, timeout)
    if local_result.get("ok"):
        return local_result

    return result



def _find(executable: str) -> str | None:
    return shutil.which(executable)


def _python_command() -> str:
    return sys.executable or "python"


async def _run_process(
    argv: list[str],
    cwd: str,
    stdin_data: str,
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Run ``argv`` in ``cwd``, feed ``stdin_data``, and capture output."""
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(stdin_data.encode("utf-8", errors="replace")),
            timeout=timeout,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return {
            "ok": True,
            "timed_out": True,
            "stdout": "",
            "stderr": "Execution timed out.",
        }
    return {
        "ok": True,
        "timed_out": False,
        "stdout": stdout.decode("utf-8", errors="replace")[:MAX_CAPTURE_BYTES],
        "stderr": stderr.decode("utf-8", errors="replace")[:MAX_CAPTURE_BYTES],
    }


def normalize_output(text: str | None) -> str:
    """Normalize output for comparison: strip line trailing whitespace and blank tail lines."""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


async def execute_local(
    language: str,
    source: str,
    stdin_data: str = "",
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Execute ``source`` locally for ``language``.

    Returns a dict with:
      * ``ok``            - the toolchain ran (False only for unsupported language)
      * ``missing_runtime`` - a required runtime/compiler is not installed
      * ``timed_out``     - the program exceeded the timeout
      * ``stdout``/``stderr`` - captured output
      * ``error``         - human-readable message when the run could not start
    """
    lang = (language or "").lower().strip()

    if lang == "csharp":
        return _missing_runtime("Mono/.NET (csc)", lang)

    if lang not in ("python", "javascript", "c", "c++", "cpp", "java"):
        return {
            "ok": False,
            "missing_runtime": False,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "error": f"Language '{language}' is not supported by the local runner.",
        }

    with tempfile.TemporaryDirectory(prefix="aico_") as tmp:
        work = Path(tmp)

        if lang == "python":
            script = work / "main.py"
            script.write_text(source, encoding="utf-8")
            return await _run_process(
                [_python_command(), "-u", str(script)], str(work), stdin_data, timeout
            )

        if lang == "javascript":
            node = _find("node")
            if not node:
                return _missing_runtime("node", lang)
            script = work / "main.js"
            script.write_text(source, encoding="utf-8")
            return await _run_process([node, str(script)], str(work), stdin_data, timeout)

        if lang in ("c", "c++", "cpp"):
            compiler = _find("gcc") or _find("g++")
            if not compiler:
                return _missing_runtime("gcc/g++", lang)
            src = work / "main.c"
            src.write_text(source, encoding="utf-8")
            exe = work / ("main.exe" if os.name == "nt" else "main")
            compiled = await _run_process(
                [compiler, str(src), "-o", str(exe)], str(work), "", timeout
            )
            if compiled["stderr"]:
                return compiled
            return await _run_process([str(exe)], str(work), stdin_data, timeout)

        if lang == "java":
            javac = _find("javac")
            java = _find("java")
            if not javac or not java:
                return _missing_runtime("javac/java", lang)
            match = re.search(r"\b(?:public\s+)?class\s+(\w+)", source)
            class_name = match.group(1) if match else "Main"
            src = work / f"{class_name}.java"
            src.write_text(source, encoding="utf-8")
            compiled = await _run_process([javac, str(src)], str(work), "", timeout)
            if compiled["stderr"]:
                return compiled
            return await _run_process(
                [java, "-cp", str(work), class_name], str(work), stdin_data, timeout
            )

    return {
        "ok": False,
        "missing_runtime": False,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "error": f"Language '{language}' is not supported by the local runner.",
    }


def _missing_runtime(runtime: str, language: str) -> dict[str, Any]:
    return {
        "ok": False,
        "missing_runtime": True,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "error": f"The {runtime} runtime is not installed on this server, so {language} "
        "code cannot be executed locally.",
    }
