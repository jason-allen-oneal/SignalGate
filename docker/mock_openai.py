from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="mock-openai")


@app.post("/v1/chat/completions")
async def chat_completions(req: Request):
    payload: dict[str, Any] = await req.json()
    stream = bool(payload.get("stream"))

    model = payload.get("model", "mock-model")

    if stream:
        async def gen():
            chunk = {
                "id": "mock-stream-1",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}}],
            }
            yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    body = {
        "id": "mock-1",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return JSONResponse(body)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
