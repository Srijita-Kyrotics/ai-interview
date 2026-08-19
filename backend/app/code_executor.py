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

Security features:
- Resource limits (CPU time, memory, file descriptors)
- Compilation caching for faster repeated runs
- Optional Docker sandboxing for complete isolation
- Output size limits to prevent DoS
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

EXEC_TIMEOUT_SECONDS = 5.0
MAX_CAPTURE_BYTES = 64 * 1024
MAX_MEMORY_MB = 256
MAX_CPU_SECONDS = 10

# Compilation cache: {cache_key: (executable_path, timestamp)}
_compilation_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour

logger = logging.getLogger("ai_interview.code_executor")


def _find(executable: str) -> str | None:
    return shutil.which(executable)


def _python_command() -> str:
    return sys.executable or "python"


def _get_cache_key(language: str, source: str) -> str:
    """Generate a cache key for compilation results."""
    content = f"{language}:{source}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_cached_executable(cache_key: str) -> str | None:
    """Retrieve cached executable if it exists and hasn't expired."""
    if cache_key in _compilation_cache:
        exe_path, timestamp = _compilation_cache[cache_key]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            # Check if file still exists
            if os.path.exists(exe_path):
                return exe_path
            else:
                del _compilation_cache[cache_key]
    return None


def _cache_executable(cache_key: str, exe_path: str) -> None:
    """Cache a compiled executable."""
    _compilation_cache[cache_key] = (exe_path, time.time())
    # Cleanup old cache entries
    now = time.time()
    expired = [k for k, (_, ts) in _compilation_cache.items() if now - ts > _CACHE_TTL_SECONDS]
    for k in expired:
        del _compilation_cache[k]


def _apply_resource_limits() -> None:
    """Apply resource limits to the current process (Linux only)."""
    if os.name != "posix":
        return
    try:
        import resource
        # Limit CPU time
        resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS))
        # Limit memory
        memory_bytes = MAX_MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        # Limit file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        # Limit file size
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_CAPTURE_BYTES, MAX_CAPTURE_BYTES))
    except Exception as e:
        logger.debug("Could not apply resource limits: %s", e)


async def _run_process(
    argv: list[str],
    cwd: str,
    stdin_data: str,
    timeout: float = EXEC_TIMEOUT_SECONDS,
    apply_limits: bool = True,
) -> dict[str, Any]:
    """Run ``argv`` in ``cwd``, feed ``stdin_data``, and capture output."""
    if os.name == "posix" and apply_limits:
        # Use preexec_fn to apply limits in child process
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=_apply_resource_limits,
        )
    else:
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
    use_cache: bool = True,
) -> dict[str, Any]:
    """Execute ``source`` locally for ``language``.

    Returns a dict with:
      * ``ok``            - the toolchain ran (False only for unsupported language)
      * ``missing_runtime`` - a required runtime/compiler is not installed
      * ``timed_out``     - the program exceeded the timeout
      * ``stdout``/``stderr`` - captured output
      * ``error``         - human-readable message when the run could not start
      * ``cached``        - whether compilation was cached
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

    # Check cache for compiled languages
    cache_key = _get_cache_key(lang, source) if use_cache and lang in ("c", "c++", "cpp", "java") else None
    cached_exe = _get_cached_executable(cache_key) if cache_key else None

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

            # Use cached executable if available
            if cached_exe and os.path.exists(cached_exe):
                import shutil as sh
                try:
                    sh.copy2(cached_exe, exe)
                    logger.debug("Using cached executable for %s", lang)
                except Exception:
                    cached_exe = None

            if not cached_exe:
                compiled = await _run_process(
                    [compiler, str(src), "-o", str(exe)], str(work), "", timeout
                )
                if compiled["stderr"]:
                    return compiled
                # Cache the executable
                if cache_key and exe.exists():
                    _cache_executable(cache_key, str(exe))
            else:
                # Verify cached executable works
                test_result = await _run_process([str(exe)], str(work), "", 1.0)
                if test_result["stderr"] or test_result["timed_out"]:
                    # Cache miss - recompile
                    compiled = await _run_process(
                        [compiler, str(src), "-o", str(exe)], str(work), "", timeout
                    )
                    if compiled["stderr"]:
                        return compiled
                    if cache_key:
                        _cache_executable(cache_key, str(exe))

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

            if cached_exe and os.path.exists(cached_exe):
                # For Java, cached_exe would be the directory with .class files
                import shutil as sh
                try:
                    sh.copytree(cached_exe, work, dirs_exist_ok=True)
                    logger.debug("Using cached Java classes")
                except Exception:
                    cached_exe = None

            if not cached_exe:
                compiled = await _run_process([javac, str(src)], str(work), "", timeout)
                if compiled["stderr"]:
                    return compiled
                # Cache the compiled class files
                if cache_key:
                    class_dir = work / "classes"
                    class_dir.mkdir(exist_ok=True)
                    # Move .class files to cache
                    for class_file in work.glob("*.class"):
                        import shutil as sh
                        sh.move(str(class_file), str(class_dir / class_file.name))
                    _cache_executable(cache_key, str(class_dir))
            else:
                # Verify cached classes work
                test_result = await _run_process(
                    [java, "-cp", str(work), class_name], str(work), "", 1.0
                )
                if test_result["stderr"] or test_result["timed_out"]:
                    compiled = await _run_process([javac, str(src)], str(work), "", timeout)
                    if compiled["stderr"]:
                        return compiled
                    if cache_key:
                        class_dir = work / "classes"
                        class_dir.mkdir(exist_ok=True)
                        for class_file in work.glob("*.class"):
                            import shutil as sh
                            sh.move(str(class_file), str(class_dir / class_file.name))
                        _cache_executable(cache_key, str(class_dir))

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


async def execute_docker_sandbox(
    language: str,
    source: str,
    stdin_data: str = "",
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """
    Execute code in a Docker sandbox for complete isolation.

    Requires Docker to be available and appropriate images pulled.
    Images: python:3.12-slim, node:20-slim, gcc:latest, openjdk:21-slim
    """
    lang = (language or "").lower().strip()

    docker_images = {
        "python": "python:3.12-slim",
        "javascript": "node:20-slim",
        "c": "gcc:latest",
        "c++": "gcc:latest",
        "cpp": "gcc:latest",
        "java": "openjdk:21-slim",
    }

    if lang not in docker_images:
        return {
            "ok": False,
            "missing_runtime": True,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "error": f"Docker sandbox not available for language '{language}'.",
        }

    image = docker_images[lang]

    # Prepare command based on language
    if lang == "python":
        cmd = ["python3", "-u", "/tmp/main.py"]
        file_name = "main.py"
    elif lang == "javascript":
        cmd = ["node", "/tmp/main.js"]
        file_name = "main.js"
    elif lang in ("c", "c++", "cpp"):
        cmd = ["sh", "-c", "gcc /tmp/main.c -o /tmp/main && /tmp/main"]
        file_name = "main.c"
    elif lang == "java":
        # For Java, we need to extract class name
        match = re.search(r"\b(?:public\s+)?class\s+(\w+)", source)
        class_name = match.group(1) if match else "Main"
        cmd = ["sh", "-c", f"javac /tmp/{class_name}.java && java -cp /tmp {class_name}"]
        file_name = f"{class_name}.java"
    else:
        return {
            "ok": False,
            "missing_runtime": True,
            "timed_out": False,
            "stdout": "",
            "stderr": "",
            "error": f"Unsupported language for Docker: {language}",
        }

    # Write source to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix=f".{file_name.split('.')[-1]}", delete=False) as f:
        f.write(source)
        temp_path = f.name

    try:
        # Run in Docker
        docker_cmd = [
            "docker", "run", "--rm",
            "--memory", f"{MAX_MEMORY_MB}m",
            "--cpus", "1.0",
            "--pids-limit", "64",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=100m",
            "-v", f"{temp_path}:/tmp/{file_name}:ro",
            image
        ] + cmd

        proc = await asyncio.create_subprocess_exec(
            *docker_cmd,
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
                "stderr": "Execution timed out in Docker sandbox.",
            }

        return {
            "ok": True,
            "timed_out": False,
            "stdout": stdout.decode("utf-8", errors="replace")[:MAX_CAPTURE_BYTES],
            "stderr": stderr.decode("utf-8", errors="replace")[:MAX_CAPTURE_BYTES],
        }

    finally:
        # Cleanup temp file
        try:
            os.unlink(temp_path)
        except Exception:
            pass


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


def clear_compilation_cache() -> int:
    """Clear the compilation cache and return number of entries removed."""
    count = len(_compilation_cache)
    _compilation_cache.clear()
    return count


def get_cache_stats() -> dict:
    """Get compilation cache statistics."""
    return {
        "entries": len(_compilation_cache),
        "languages": list(set(k.split(":")[0] for k in _compilation_cache.keys())) if _compilation_cache else [],
    }
