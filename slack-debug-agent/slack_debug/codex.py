"""Small JSON-lines client for the pinned Codex app-server protocol."""

import asyncio
import contextlib
import json
import os
import signal


class Codex:
    def __init__(self, config, on_request):
        self.config = config
        self.on_request = on_request
        self.process = None
        self.pending = {}
        self.requests = set()
        self.events = asyncio.Queue()
        self.sequence = 0
        self.reader = None
        self.stderr = None
        self.items = {}

    async def start(self, instructions):
        self.process = await asyncio.create_subprocess_exec(
            self.config.codex_bin,
            "app-server",
            "--stdio",
            "--disable",
            "hooks",
            "--disable",
            "multi_agent",
            "--disable",
            "multi_agent_v2",
            "-c",
            'approval_policy="on-request"',
            "-c",
            'approvals_reviewer="user"',
            "-c",
            'sandbox_mode="workspace-write"',
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c",
            "sandbox_workspace_write.exclude_slash_tmp=true",
            cwd=self.config.root,
            env=self.config.child_environment(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            limit=16 * 1024 * 1024,
        )
        self.reader = asyncio.create_task(self._read())
        self.stderr = asyncio.create_task(self._drain_stderr())
        await self.call(
            "initialize", {"clientInfo": {"name": "silica_slack_debug", "version": "0.1.0"}}
        )
        await self.send({"method": "initialized", "params": {}})
        result = await self.call(
            "thread/start",
            {
                "cwd": str(self.config.root),
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandbox": "workspace-write",
                "ephemeral": True,
                "developerInstructions": instructions,
            },
        )
        self.thread_id = result["thread"]["id"]
        self.session_id = result["thread"].get("sessionId") or self.thread_id
        return self.thread_id

    async def send(self, message):
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        await self.process.stdin.drain()

    async def call(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, 60)
        except TimeoutError as error:
            raise RuntimeError(f"Codex {method} did not respond within 60s") from error
        finally:
            self.pending.pop(request_id, None)

    async def _answer(self, message):
        try:
            result = await self.on_request(message["method"], message.get("params", {}))
            await self.send({"id": message["id"], "result": result})
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with contextlib.suppress(ConnectionError):
                await self.send(
                    {
                        "id": message["id"],
                        "error": {
                            "code": -32601,
                            "message": "Request unsupported or could not be safely reviewed",
                        },
                    }
                )
            reason = (
                str(error)
                if isinstance(error, (ValueError, RuntimeError))
                else type(error).__name__
            )
            await self.events.put({"method": "client/failure", "params": {"reason": reason}})

    async def _read(self):
        try:
            while line := await self.process.stdout.readline():
                message = json.loads(line)
                if "method" in message:
                    if message["method"] == "item/started":
                        item = message.get("params", {}).get("item", {})
                        if item.get("type") == "fileChange":
                            self.items[item["id"]] = item
                    if "id" in message:
                        task = asyncio.create_task(self._answer(message))
                        self.requests.add(task)
                        task.add_done_callback(self.requests.discard)
                    else:
                        # Command output and reasoning can be large; neither is posted to Slack.
                        if message["method"] in (
                            "item/started",
                            "item/completed",
                            "turn/completed",
                            "error",
                        ):
                            await self.events.put(message)
                elif message.get("id") in self.pending:
                    future = self.pending[message["id"]]
                    if not future.done():
                        if "error" in message:
                            future.set_exception(
                                RuntimeError(
                                    f"Codex RPC failed: {message['error'].get('message', 'unknown error')}"
                                )
                            )
                        else:
                            future.set_result(message.get("result", {}))
            raise RuntimeError("Codex app-server exited")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            for future in list(self.pending.values()):
                if not future.done():
                    future.set_exception(RuntimeError(str(error)))
            await self.events.put({"method": "client/failure", "params": {"reason": str(error)}})

    async def _drain_stderr(self):
        # Drain without logging: diagnostic output can contain issue data or credentials.
        while await self.process.stderr.read(8192):
            pass

    async def turn(self, text):
        self.items.clear()
        result = await self.call(
            "turn/start",
            {
                "threadId": self.thread_id,
                "input": [{"type": "text", "text": text}],
            },
        )
        turn_id = result["turn"]["id"]
        answer = []
        while True:
            message = await self.events.get()
            method, params = message["method"], message.get("params", {})
            if method == "client/failure":
                raise RuntimeError(params["reason"])
            if method == "error" and not params.get("willRetry", False):
                raise RuntimeError(params.get("error", {}).get("message", "Codex turn failed"))
            if params.get("turnId", turn_id) != turn_id:
                continue
            if method == "item/completed":
                item = params["item"]
                if item["type"] == "agentMessage" and item.get("phase") != "commentary":
                    answer.append(item["text"])
            elif method == "turn/completed" and params["turn"]["id"] == turn_id:
                turn = params["turn"]
                if turn["status"] != "completed":
                    raise RuntimeError(
                        (turn.get("error") or {}).get("message", f"turn {turn['status']}")
                    )
                if not answer:
                    raise RuntimeError("Codex completed without a response")
                return "\n\n".join(answer)

    async def close(self):
        if self.process:
            # Kill the whole session process group, including commands and tunnels it owns.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGTERM)
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.process.wait(), 5)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)
            await self.process.wait()
        tasks = [t for t in (self.reader, self.stderr, *self.requests) if t]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
