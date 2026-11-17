"""Shared admission control for decoding, camera capture and CPU processing."""

from fastapi import HTTPException, Request


def processing_slot(request: Request):
    slot = request.app.state.processing_slot
    if not slot.acquire(blocking=False):
        raise HTTPException(503, "Another frame is processing. Retry after it completes.", headers={"Retry-After": "1"})
    try:
        yield
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        slot.release()
