"""Chat router with streaming responses from the chat agent."""
import json
import logging
import traceback
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage

from app.database import get_db
from app.models import ChatMessage
from app.schemas import ChatRequest, ChatMessageResponse
from app.agents.chat_agent import chat_agent
from app.utils.streaming import sse_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    """Chat endpoint with SSE streaming. Sends thinking, tool calls, and answer tokens."""
    session_id = request.session_id
    user_message = request.message

    # Save user message
    db_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=user_message,
    )
    db.add(db_msg)
    db.commit()

    # Load conversation history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .limit(40)
        .all()
    )

    messages = []
    for msg in history:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))

    async def event_stream():
        yield sse_event("thinking", {"message": "Analyzing your question..."})

        combined_content = ""
        tool_calls_log = []

        try:
            async for event in chat_agent.astream_events({"messages": messages}, version="v2"):
                kind = event["event"]

                if kind == "on_tool_start":
                    # A tool is being called — stream to UI
                    tool_name = event["name"]
                    tool_input = event["data"].get("input", {})
                    yield sse_event("tool_call", {
                        "tool": tool_name,
                        "message": f"Using {tool_name}...",
                        "input": tool_input,
                    })

                elif kind == "on_tool_end":
                    # Tool finished — stream result to UI
                    tool_name = event["name"]
                    tool_output = event["data"].get("output", "")
                    clean_output = str(tool_output)
                    if hasattr(tool_output, "content"):
                        clean_output = str(tool_output.content)

                    tool_calls_log.append({"tool": tool_name, "output": clean_output[:500]})
                    yield sse_event("tool_result", {
                        "tool": tool_name,
                        "result": clean_output,
                    })

                elif kind == "on_chat_model_stream":
                    # LLM is generating tokens (reasoning / thinking)
                    content = event["data"]["chunk"].content
                    if content and isinstance(content, str):
                        yield sse_event("thought", {"token": content})

                elif kind == "on_chain_end" and event["name"] == "LangGraph":
                    # Graph finished — extract final answer
                    final_state = event["data"]["output"]
                    final_messages = final_state.get("messages", [])
                    if final_messages:
                        last_msg = final_messages[-1]
                        if hasattr(last_msg, "content"):
                            combined_content = (
                                last_msg.content
                                if isinstance(last_msg.content, str)
                                else str(last_msg.content)
                            )

            # Persist assistant response
            db_resp = ChatMessage(
                session_id=session_id,
                role="assistant",
                content=combined_content,
                tool_calls=json.dumps(tool_calls_log) if tool_calls_log else None,
            )
            db.add(db_resp)
            db.commit()

            yield sse_event("answer", {"content": combined_content})
            yield sse_event("done", {})

        except Exception as e:
            logger.error(f"Chat agent error: {traceback.format_exc()}")
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str, db: Session = Depends(get_db)):
    """Get chat history for a session."""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str, db: Session = Depends(get_db)):
    """Clear chat history for a session."""
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.commit()
    return {"message": "Chat history cleared"}
