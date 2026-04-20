"""SSE streaming utilities for agent progress."""
import json
from typing import Dict, Any


def sse_event(event: str, data: Dict[str, Any]) -> str:
    """Format a Server-Sent Event string."""
    return f"data: {json.dumps({'event': event, **data})}\n\n"
