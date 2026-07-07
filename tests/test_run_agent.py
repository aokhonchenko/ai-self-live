import pytest

from scripts import run_agent


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.model = "fake-model"
        self.base_url = "https://example/v1"

    def complete(self, messages, tools):
        self.calls.append((list(messages), list(tools)))
        return self.replies.pop(0)


def install_fake_client(monkeypatch, client):
    monkeypatch.setattr(
        run_agent.OpenAICompatibleClient,
        "from_environment",
        classmethod(lambda cls, timeout, temperature: client),
    )


def test_read_settings_uses_agent_section(tmp_path):
    path = tmp_path / "project.toml"
    path.write_text("[agent]\nstep_limit = 2\ntemperature = 0.5\n", encoding="utf-8")

    settings = run_agent.read_settings(path)

    assert settings["step_limit"] == 2
    assert settings["temperature"] == 0.5
    assert settings["request_timeout_seconds"] == 300
    assert settings["repeated_tool_error_limit"] == 3
    assert settings["repeated_tool_call_limit"] == 3


def test_read_settings_defaults_to_long_session(tmp_path):
    settings = run_agent.read_settings(tmp_path / "missing.toml")

    assert settings["step_limit"] == 300


def test_read_task_requires_existing_prompt(tmp_path):
    with pytest.raises(run_agent.AgentError, match="Prompt file does not exist"):
        run_agent.read_task(tmp_path / "missing.md")


def test_parse_tool_arguments_rejects_invalid_json():
    with pytest.raises(run_agent.AgentError, match="not valid JSON"):
        run_agent.parse_tool_arguments("{")
    with pytest.raises(run_agent.AgentError, match="must be a JSON object"):
        run_agent.parse_tool_arguments("[]")


def test_run_agent_executes_native_tool_calls(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    settings = tmp_path / "project.toml"
    settings.write_text("[agent]\nstep_limit = 3\n", encoding="utf-8")
    client = FakeClient(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "write_file",
                            "arguments": '{"path":"state/last_session.md","content":"готово"}',
                        },
                    }
                ],
            },
            {"content": "Финал"},
        ]
    )
    install_fake_client(monkeypatch, client)

    result = run_agent.run_agent(tmp_path, prompt, settings)

    captured = capsys.readouterr()
    assert result == 0
    

def test_compact_tool_arguments_handles_write_file(tmp_path):
    result = run_agent.compact_tool_arguments(
        "write_file",
        {"path": "notes.md", "content": "hello world"},
    )

    assert result["path"] == "notes.md"
    assert result["content_bytes"] == len("hello world".encode("utf-8"))
    assert len(result["content_sha256"]) == 12


def test_compact_tool_arguments_fallback_for_other_tools(tmp_path):
    result = run_agent.compact_tool_arguments(
        "read_file",
        {"path": "notes.md"},
    )

    assert result == {"path": "notes.md"}


def test_run_agent_executes_text_protocol(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    client = FakeClient(
        [
            {'content': '{"tool":"write_file","path":"logs/history.md","content":"запись"}'},
            {'content': '{"final":"готово"}'},
        ]
    )
    install_fake_client(monkeypatch, client)

    result = run_agent.run_agent(tmp_path, prompt, tmp_path / "missing.toml")

    assert result == 0
    assert (tmp_path / "logs" / "history.md").read_text(encoding="utf-8") == "запись"
    assert client.calls[1][0][-1]["role"] == "user"


def test_run_agent_accepts_native_final_pseudo_tool(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    client = FakeClient(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-final",
                        "type": "function",
                        "function": {
                            "name": "final",
                            "arguments": '{"final":"готово"}',
                        },
                    }
                ],
            },
        ]
    )
    install_fake_client(monkeypatch, client)

    result = run_agent.run_agent(tmp_path, prompt, tmp_path / "missing.toml")

    captured = capsys.readouterr()
    assert result == 0
    assert "finished: готово" in captured.out

def test_run_agent_reports_native_tool_error_to_model(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    client = FakeClient(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"missing.md"}',
                        },
                    }
                ],
            },
            {"content": "Файл отсутствует, продолжаю без него."},
        ]
    )
    install_fake_client(monkeypatch, client)

    result = run_agent.run_agent(tmp_path, prompt, tmp_path / "missing.toml")

    captured = capsys.readouterr()
    assert result == 0
    assert "tool error: read_file" in captured.out
    observation = client.calls[1][0][-1]
    assert observation["role"] == "tool"
    assert '"ok": false' in observation["content"]
    assert "file does not exist: missing.md" in observation["content"]


def test_run_agent_reports_text_tool_error_to_model(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    client = FakeClient(
        [
            {'content': '{"tool":"read_file","path":"missing.md"}'},
            {'content': '{"final":"нет файла"}'},
        ]
    )
    install_fake_client(monkeypatch, client)

    result = run_agent.run_agent(tmp_path, prompt, tmp_path / "missing.toml")

    assert result == 0
    observation = client.calls[1][0][-1]
    assert observation["role"] == "user"
    assert '"ok": false' in observation["content"]
    assert "file does not exist: missing.md" in observation["content"]


def test_run_agent_reports_step_limit(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    settings = tmp_path / "project.toml"
    settings.write_text("[agent]\nstep_limit = 1\n", encoding="utf-8")
    client = FakeClient(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"prompt.md"}',
                        },
                    }
                ],
            }
        ]
    )
    install_fake_client(monkeypatch, client)

    with pytest.raises(run_agent.AgentError, match="step limit exceeded"):
        run_agent.run_agent(tmp_path, prompt, settings)


def test_run_agent_stops_repeated_unknown_native_tool_calls(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    settings = tmp_path / "project.toml"
    settings.write_text(
        "[agent]\nstep_limit = 10\nrepeated_tool_error_limit = 3\n",
        encoding="utf-8",
    )
    unknown_tool_reply = {
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "missing_tool",
                    "arguments": '{"value":"pytest"}',
                },
            }
        ],
    }
    client = FakeClient([unknown_tool_reply, unknown_tool_reply, unknown_tool_reply])
    install_fake_client(monkeypatch, client)

    with pytest.raises(run_agent.AgentError, match="repeated tool error 3 times: missing_tool: unknown tool"):
        run_agent.run_agent(tmp_path, prompt, settings)

    captured = capsys.readouterr()
    assert captured.out.count("tool error: missing_tool unknown tool: missing_tool") == 3
    assert len(client.calls) == 3


def test_run_agent_stops_repeated_successful_native_tool_calls(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")
    settings = tmp_path / "project.toml"
    settings.write_text(
        "[agent]\nstep_limit = 10\nrepeated_tool_call_limit = 3\n",
        encoding="utf-8",
    )
    repeated_reply = {
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "write_file",
                    "arguments": '{"path":"notes.md","content":"very secret repeated content"}',
                },
            }
        ],
    }
    client = FakeClient([repeated_reply, repeated_reply, repeated_reply])
    install_fake_client(monkeypatch, client)

    with pytest.raises(run_agent.AgentError, match="repeated tool call 3 times"):
        run_agent.run_agent(tmp_path, prompt, settings)

    captured = capsys.readouterr()
    assert captured.out.count("tool: write_file") == 3
    assert "content_bytes" in captured.out
    assert "content_sha256" in captured.out
    assert "very secret repeated content" not in captured.out
    assert len(client.calls) == 3


def test_main_returns_one_on_agent_error(tmp_path, monkeypatch, capsys):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")

    def fail_run_agent(root, prompt_file, settings_path):
        raise run_agent.AgentError("bad config")

    monkeypatch.setattr(run_agent, "run_agent", fail_run_agent)
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        ["run_agent.py", "--root", str(tmp_path), "--prompt-file", str(prompt)],
    )

    result = run_agent.main()

    captured = capsys.readouterr()
    assert result == 1
    assert "agent session failed: bad config" in captured.err

def test_system_message_uses_generated_tool_passport():
    message = run_agent.system_message("- `custom_tool()` - generated passport line.")

    assert "custom_tool" in message
    assert "src/tools/*/tool.py" in message
    assert "read_file: read a whole UTF-8 file" not in message
    

def test_execute_text_protocol_rejects_empty_tool_name(tmp_path):
    from scripts.run_agent import execute_text_protocol

    batch = execute_text_protocol(tmp_path, {"tool": "", "path": "x.md"})

    assert batch is None


def test_execute_text_protocol_handles_tool_error(tmp_path, monkeypatch):
    from scripts.run_agent import execute_text_protocol, ToolError

    def mock_call_tool(root, name, arguments):
        raise ToolError(f"tool {name} failed")

    monkeypatch.setattr(run_agent, "call_tool", mock_call_tool)

    batch = execute_text_protocol(tmp_path, {"tool": "broken_tool", "path": "x.md"})

    assert batch is not None
    assert len(batch.error_signatures) == 1
    assert "broken_tool" in batch.error_signatures[0]
    assert batch.messages[0]["role"] == "user"
    assert '"ok": false' in batch.messages[0]["content"]


def test_main_resolves_relative_prompt_file(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")

    def mock_run_agent(root, prompt_file, settings_path):
        assert prompt_file == prompt.resolve()
        assert settings_path == tmp_path / "config" / "project.toml"
        return 0

    monkeypatch.setattr(run_agent, "run_agent", mock_run_agent)
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "run_agent.py",
            "--root",
            str(tmp_path),
            "--prompt-file",
            "prompt.md",
            "--settings",
            "config/project.toml",
        ],
    )

    result = run_agent.main()

    assert result == 0


def test_main_resolves_relative_settings_file(tmp_path, monkeypatch):
    prompt = tmp_path / "prompt.md"
    prompt.write_text("task", encoding="utf-8")

    def mock_run_agent(root, prompt_file, settings_path):
        assert settings_path == tmp_path / "custom.toml"
        return 0

    monkeypatch.setattr(run_agent, "run_agent", mock_run_agent)
    monkeypatch.setattr(
        run_agent.sys,
        "argv",
        [
            "run_agent.py",
            "--root",
            str(tmp_path),
            "--prompt-file",
            str(prompt),
            "--settings",
            "custom.toml",
        ],
    )

    result = run_agent.main()

    assert result == 0
