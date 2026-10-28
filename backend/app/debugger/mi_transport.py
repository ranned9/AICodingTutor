from __future__ import annotations
import os
import subprocess
import threading
import queue
import time
from typing import Any

from .mi_parser import parse_record
from .models import MIRecord


class GdbExitedError(Exception):
    pass


class CommandTimeoutError(Exception):
    pass


class MITransport:
    def __init__(self, gdb_path: str):
        self._gdb_path = gdb_path
        self._proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._token_counter = 0
        self._token_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[int, list] = {}
        self._pending_lock = threading.Lock()
        self._event_queue: queue.Queue = queue.Queue()
        self._stderr_lines: list[str] = []
        self._exited = False
        self._exit_reason = ""

    @property
    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and not self._exited

    def start(self, cwd: str | None = None) -> None:
        env = os.environ.copy()
        gdb_dir = os.path.dirname(self._gdb_path)
        if gdb_dir:
            env["PATH"] = gdb_dir + os.pathsep + env.get("PATH", "")
        self._proc = subprocess.Popen(
            [self._gdb_path, "--quiet", "--nx", "--interpreter=mi2"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_thread.start()

    def _read_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        try:
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    break
                line = line.rstrip("\n\r")
                if not line:
                    continue
                rec = parse_record(line)
                if rec is None:
                    continue
                if rec.kind == "result" and rec.token is not None:
                    with self._pending_lock:
                        if rec.token in self._pending:
                            self._pending[rec.token][0].append(rec)
                            event = self._pending[rec.token][1]
                            if event is not None:
                                event.set()
                elif rec.kind == "exec" or rec.kind == "notify":
                    self._event_queue.put(rec)
        except Exception:
            pass
        finally:
            self._exited = True
            self._event_queue.put(None)
            with self._pending_lock:
                for token, lst in self._pending.items():
                    event = lst[1] if len(lst) > 1 else None
                    if event is not None and not event.is_set():
                        lst[0].append(None)
                        event.set()

    def _stderr_loop(self) -> None:
        assert self._proc is not None
        assert self._proc.stderr is not None
        try:
            for line in self._proc.stderr:
                self._stderr_lines.append(line.rstrip("\n\r"))
        except Exception:
            pass

    def command(self, mi_cmd: str, timeout: float = 10.0) -> MIRecord:
        if not self.is_alive:
            raise GdbExitedError("GDB process is not alive")
        with self._token_lock:
            self._token_counter += 1
            token = self._token_counter
        event = threading.Event()
        with self._pending_lock:
            self._pending[token] = [[], event]
        full_cmd = f"{token}{mi_cmd}\n"
        with self._write_lock:
            assert self._proc is not None
            assert self._proc.stdin is not None
            self._proc.stdin.write(full_cmd)
            self._proc.stdin.flush()
        if not event.wait(timeout=timeout):
            with self._pending_lock:
                self._pending.pop(token, None)
            raise CommandTimeoutError(f"Command timed out: {mi_cmd} (token={token})")
        with self._pending_lock:
            lst = self._pending.pop(token, [[], event])
        results = lst[0]
        if not results:
            raise GdbExitedError(f"GDB exited while waiting for: {mi_cmd}")
        return results[0]

    def wait_for_stop(self, timeout: float = 10.0) -> MIRecord:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CommandTimeoutError("Timed out waiting for *stopped")
            try:
                rec = self._event_queue.get(timeout=remaining)
            except queue.Empty:
                raise CommandTimeoutError("Timed out waiting for *stopped")
            if rec is None:
                raise GdbExitedError("GDB exited while waiting for stop")
            if rec.kind == "exec" and rec.klass == "stopped":
                return rec

    def drain_events(self) -> list[MIRecord]:
        events = []
        while True:
            try:
                rec = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if rec is not None:
                events.append(rec)
        return events

    @property
    def stderr_text(self) -> str:
        return "\n".join(self._stderr_lines)

    def close(self, graceful: bool = True) -> None:
        if self._proc is None:
            return
        if graceful and self.is_alive:
            try:
                with self._write_lock:
                    assert self._proc.stdin is not None
                    self._proc.stdin.write("-gdb-exit\n")
                    self._proc.stdin.flush()
                self._proc.wait(timeout=3)
            except Exception:
                pass
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
        self._proc = None
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1)