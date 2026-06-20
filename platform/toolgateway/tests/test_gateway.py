from workbench_toolgateway import ToolGateway, ToolSpec, build_default_gateway


def _echo(args: dict) -> dict:
    return {"echo": args.get("v")}


async def test_register_and_call_records_audit():
    gw = ToolGateway()
    gw.register(ToolSpec(name="echo", description="d"), _echo)

    result = await gw.call("echo", {"v": 1})
    assert result.allowed is True
    assert result.output == {"echo": 1}
    assert len(gw.audit) == 1
    assert gw.audit[0].tool == "echo" and gw.audit[0].allowed is True


async def test_allowlist_denies_without_executing():
    executed = {"ran": False}

    def handler(args):
        executed["ran"] = True
        return {}

    gw = ToolGateway()
    gw.register(ToolSpec(name="danger", description="d"), handler)
    result = await gw.call("danger", {}, allowlist={"other"})

    assert result.allowed is False
    assert result.error == "tool not permitted"
    assert executed["ran"] is False  # denied tools never run
    assert gw.audit[0].allowed is False  # denial is audited


async def test_audit_sink_called_on_allowed_and_denied():
    captured = []

    gw = ToolGateway(audit_sink=captured.append)
    gw.register(ToolSpec(name="echo", description="d"), _echo)

    await gw.call("echo", {"v": 1}, allowlist={"echo"})  # allowed
    await gw.call("echo", {"v": 2}, allowlist={"other"})  # denied by allowlist

    assert len(captured) == 2  # sink fires for both allowed and denied
    assert captured[0].tool == "echo" and captured[0].allowed is True
    assert captured[1].allowed is False and captured[1].error == "tool not permitted"
    # in-memory audit list is still populated alongside the sink (back-compat)
    assert len(gw.audit) == 2


async def test_denied_call_is_recorded_in_audit():
    gw = ToolGateway()
    gw.register(ToolSpec(name="danger", description="d"), _echo)

    result = await gw.call("danger", {"v": 1}, allowlist={"safe"})

    assert result.allowed is False
    assert len(gw.audit) == 1
    assert gw.audit[0].tool == "danger"
    assert gw.audit[0].allowed is False
    assert gw.audit[0].error == "tool not permitted"


async def test_audit_sink_failure_does_not_break_call():
    def boom_sink(_entry):
        raise RuntimeError("sink down")

    gw = ToolGateway(audit_sink=boom_sink)
    gw.register(ToolSpec(name="echo", description="d"), _echo)

    result = await gw.call("echo", {"v": 1})  # must not raise
    assert result.allowed is True and result.output == {"echo": 1}


async def test_unknown_tool():
    gw = ToolGateway()
    result = await gw.call("ghost", {})
    assert result.allowed is False and result.error == "unknown tool"


async def test_handler_error_is_returned_not_raised():
    def boom(args):
        raise ValueError("nope")

    gw = ToolGateway()
    gw.register(ToolSpec(name="boom", description="d"), boom)
    result = await gw.call("boom", {})
    assert result.allowed is True and "nope" in result.error
    assert gw.audit[0].error and "nope" in gw.audit[0].error


# --- default connectors ---


async def test_default_gateway_lists_three_tools():
    gw = build_default_gateway()
    names = {t.name for t in gw.list_tools()}
    assert names == {"web_search", "fetch", "kb_search"}


async def test_web_search_then_fetch_flow():
    gw = build_default_gateway()
    allow = {"web_search", "fetch"}

    search = await gw.call(
        "web_search", {"query": "retrieval augmented generation"}, allowlist=allow
    )
    assert search.allowed and len(search.output) >= 1
    top_url = search.output[0]["url"]

    fetched = await gw.call("fetch", {"url": top_url}, allowlist=allow)
    assert fetched.allowed
    assert fetched.output["url"] == top_url
    assert "retrieval" in fetched.output["text"].lower()


async def test_fetch_unknown_url_errors():
    gw = build_default_gateway()
    result = await gw.call("fetch", {"url": "https://evil.example/x"}, allowlist={"fetch"})
    assert "unknown url" in result.error


async def test_kb_search_denied_when_not_allowlisted():
    gw = build_default_gateway()
    result = await gw.call("kb_search", {"query": "evals"}, allowlist={"web_search"})
    assert result.allowed is False
