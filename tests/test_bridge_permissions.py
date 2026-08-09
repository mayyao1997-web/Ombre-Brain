from bridge.start_bridge import ALLOWED_TOOLS, DENIED_TOOLS, build_config


def test_physical_187_receives_all_current_ombre_tools():
    expected = {
        "pulse",
        "breath",
        "hold",
        "grow",
        "trace",
        "links",
        "link_buckets",
    }
    assert set(ALLOWED_TOOLS) == expected
    assert DENIED_TOOLS == []

    config = build_config(
        "wss://example.invalid/mcp/?token=redacted",
        "http://127.0.0.1:8000/mcp",
        "x" * 32,
    )
    tools = config["mcpServers"]["ombre-187"]["tools"]
    assert set(tools["allow"]) == expected
    assert tools["deny"] == []
