from __future__ import annotations

import io

from munshi_apply_native.native_messaging import read_message, write_message


def test_native_message_round_trip() -> None:
    stream = io.BytesIO()
    write_message(stream, {"type": "PING"})
    stream.seek(0)
    assert read_message(stream) == {"type": "PING"}
