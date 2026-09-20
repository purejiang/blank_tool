#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Process-tree lifecycle helpers (standard library only).

A cancelled run must stop the *work* it started, not just the shell that
fronts it: ``cmd /c <string>`` makes the real command a grandchild, so
``Popen.terminate()`` on the immediate child leaves the work running.

Two layers:

1. **Job objects (Windows)**.  A job is created and the child is assigned to
   it *immediately after* ``Popen`` returns.  Job membership is inherited by
   every process the child spawns, so assigning early is the only point at
   which the whole future tree can be captured — enrolling an already-running
   process only captures that one process.  Cancellation calls
   ``TerminateJobObject``, which kills the entire tree atomically.
2. **Fallbacks**.  ``taskkill /F /T /PID`` on Windows and ``os.killpg`` on
   POSIX, used when no job handle exists (job creation failed, or the process
   was started by a code path that does not create one).

Enrolment is strictly handle-based (``Popen._handle``): resolving a bare PID
is never attempted, because that could put an unrelated process into the job
and a later ``TerminateJobObject`` would kill it.

Note the deliberate absence of ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``: closing
the handle must NOT kill anything, because descendants outliving their command
are legitimate (``adb start-server`` leaves a daemon behind, and that daemon has
to survive the node that started it).  Only an explicit cancel terminates the
tree, so normal completion keeps the pre-existing behaviour.
"""

import os
import signal
import subprocess
import threading
import time
from typing import Any, Dict, Optional

IS_WINDOWS = os.name == "nt"

#: How long :func:`terminate_tree` waits for a graceful exit before SIGKILL.
DEFAULT_GRACE_SECONDS = 5.0

#: ``taskkill`` must not flash a console window.
_CREATE_NO_WINDOW = 0x08000000

#: Exit code reported for a process terminated through a job object.
_JOB_TERMINATE_EXIT_CODE = 1

#: Serialises take-and-dispose of a job handle so two cancellation paths can
#: never act on the same handle twice.
_JOB_LOCK = threading.Lock()


def spawn_options() -> Dict[str, Any]:
    """Platform-specific ``subprocess.Popen`` keyword arguments.

    POSIX children get their own session, which is what makes
    ``os.killpg(getpgid(pid))`` able to reach the whole group.

    Windows deliberately adds **no** ``CREATE_NEW_PROCESS_GROUP``: keeping
    children inside the console process group means a console Ctrl+C still
    reaches them for free, and tree cleanup is the job object's job.
    """
    if IS_WINDOWS:
        return {}
    return {"start_new_session": True}


# ---------------------------------------------------------------------------
# Windows job objects
# ---------------------------------------------------------------------------

if IS_WINDOWS:  # pragma: no cover - exercised only on Windows
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]

    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]

    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    # Read-only existence probe.  Requested with SYNCHRONIZE only — never
    # PROCESS_TERMINATE — because ``os.kill(pid, 0)`` is *not* a safe liveness
    # check on Windows: any signal other than the two console events makes it
    # call ``TerminateProcess``, i.e. the probe would kill the target.
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]

    _SYNCHRONIZE = 0x00100000
    _WAIT_TIMEOUT = 0x00000102


def create_job() -> Optional[int]:
    """Create an anonymous job object.

    Returns the handle as an ``int``, or ``None`` on non-Windows platforms and
    whenever the object could not be created.
    """
    if not IS_WINDOWS:  # pragma: no cover - platform guard
        return None
    handle = _kernel32.CreateJobObjectW(None, None)
    if not handle:
        return None
    return int(handle)


def assign_to_job(job: Optional[int], process: Any) -> bool:
    """Enrol *process* into *job* so its future children join as well.

    ``process`` must be a real ``subprocess.Popen``, which on Windows always
    exposes its process handle as ``_handle``.  Anything else is refused:
    resolving a bare PID with ``OpenProcess`` would risk enrolling an
    *unrelated* process (a recycled PID, or a stub) into the job, where a later
    ``TerminateJobObject`` would kill it.
    """
    if not IS_WINDOWS or not job:  # pragma: no cover - platform guard
        return False

    raw_handle = getattr(process, "_handle", None)
    handle = int(raw_handle) if raw_handle else 0
    if not handle:
        return False
    try:
        return bool(
            _kernel32.AssignProcessToJobObject(
                wintypes.HANDLE(job), wintypes.HANDLE(handle)
            )
        )
    except Exception:
        return False


def terminate_job(job: Optional[int]) -> bool:
    """Kill every process in *job* without closing the handle."""
    if not IS_WINDOWS or not job:  # pragma: no cover - platform guard
        return False
    try:
        return bool(
            _kernel32.TerminateJobObject(
                wintypes.HANDLE(job), _JOB_TERMINATE_EXIT_CODE
            )
        )
    except Exception:
        return False


def close_job_handle(job: Optional[int]) -> None:
    """Release *job*.  Deliberately kills nothing — see the module docstring."""
    if not IS_WINDOWS or not job:  # pragma: no cover - platform guard
        return
    try:
        _kernel32.CloseHandle(wintypes.HANDLE(job))
    except Exception:
        pass


def attach_job(process: Any, holder: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Create a job for *process* and record its handle.

    Call this immediately after ``Popen`` returns: the assignment has to
    happen before the child spawns anything, because job membership is
    inherited and cannot be granted retroactively.

    Args:
        process: the freshly spawned ``subprocess.Popen``.
        holder: optional mapping the handle is stored in (``holder["job"]``)
            so an out-of-band cancellation path can reach it.  The returned
            handle must otherwise be released by the caller.

    Returns:
        The job handle, or ``None`` when the platform is not Windows or the
        job could not be created/assigned (callers fall back to tree tools).
    """
    job = create_job()
    if job is None:
        return None
    if not assign_to_job(job, process):
        close_job_handle(job)
        return None
    if holder is not None:
        holder["job"] = job
    return job


def terminate_job_in(holder: Optional[Dict[str, Any]]) -> bool:
    """Atomically take the job handle out of *holder* and terminate its tree.

    Returns ``True`` when a job was present.  Taking the handle under a lock
    guarantees that a cancellation racing with the executor's own cleanup can
    never operate on the same handle twice.
    """
    job = _take_job(holder)
    if job is None:
        return False
    terminate_job(job)
    close_job_handle(job)
    return True


def close_job_in(holder: Optional[Dict[str, Any]]) -> bool:
    """Atomically take the job handle out of *holder* and release it.

    Used on the normal completion path: the handle is freed without killing
    anything, so descendants that are meant to outlive the command survive.
    """
    job = _take_job(holder)
    if job is None:
        return False
    close_job_handle(job)
    return True


def _take_job(holder: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(holder, dict):
        return None
    with _JOB_LOCK:
        return holder.pop("job", None)


# ---------------------------------------------------------------------------
# Tree termination without a job handle
# ---------------------------------------------------------------------------


def terminate_tree(pid: int, grace: float = DEFAULT_GRACE_SECONDS) -> bool:
    """Kill *pid* and its descendants when no job handle is available.

    Returns ``True`` when a tree-wide strategy was applied, and ``False`` when
    no safe strategy existed — the caller then falls back to
    ``Popen.terminate()`` on the direct child.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if IS_WINDOWS:
        return _taskkill_tree(pid, grace)
    return _killpg_tree(pid, grace)


def _taskkill_tree(pid: int, grace: float) -> bool:
    """Run ``taskkill /F /T /PID``.

    Covers a live parent plus its children.  It misses grandchildren whose
    parent already exited (they get re-parented) — the case the job object
    exists for.
    """
    try:
        completed = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
            timeout=max(grace, 1.0),
        )
    except Exception:
        return False
    return completed.returncode == 0


def _killpg_tree(pid: int, grace: float) -> bool:
    """SIGTERM *pid*'s process group, escalating to SIGKILL after *grace*."""
    try:
        pgid = os.getpgid(pid)
    except OSError:
        return False
    try:
        if pgid == os.getpgid(0):
            # The child never got its own session, so signalling the group
            # would kill this process as well.
            return False
    except OSError:
        return False
    try:
        os.killpg(pgid, signal.SIGTERM)
    except OSError:
        return False
    deadline = time.monotonic() + max(grace, 0.0)
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass
    return True


def pid_alive(pid: int) -> bool:
    """Return True while *pid* still refers to a live process.

    Platform-correct on purpose.  On Windows the obvious ``os.kill(pid, 0)``
    idiom would *terminate* the process (see the ``OpenProcess`` binding
    above), so a handle wait is used instead: a signalled handle means the
    process has exited.  Only ``SYNCHRONIZE`` is requested, so this probe can
    never kill anything.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False

    if IS_WINDOWS:  # pragma: no cover - exercised only on Windows
        handle = _kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            # A dead, already-reaped PID cannot be opened; a live one always can.
            return False
        try:
            return (
                _kernel32.WaitForSingleObject(wintypes.HANDLE(handle), 0)
                == _WAIT_TIMEOUT
            )
        except Exception:
            return True
        finally:
            _kernel32.CloseHandle(wintypes.HANDLE(handle))

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True
