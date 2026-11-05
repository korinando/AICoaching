"""Answering over the interview WebSocket, for tests that aren't about the socket itself."""

from app.core.security import create_token


def answer_on_socket(
    client, session_id: int, user_id: int, text: str | None = None, recording: bytes | None = None
) -> list[dict]:
    """One typed or spoken answer on a new connection: every message up to the end of the reply,
    or up to an error."""
    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        socket.send_json({"type": "auth", "token": create_token(user_id, "access")})
        if recording is not None:
            socket.send_bytes(recording)
        else:
            socket.send_json({"type": "text_answer", "text": text})
        messages = []
        while not messages or messages[-1]["type"] not in ("turn_complete", "error"):
            messages.append(socket.receive_json())
    return messages
