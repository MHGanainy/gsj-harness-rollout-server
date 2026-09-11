"""Generated-lock reader contracts characterized on the 0.1.16 source.

Both entrypoints read JSON objects without changing the files. Failure types,
messages and exception chaining distinguish absent, unreadable and wrong-shape
locks; their module globals remain resolved when called.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import ingest_corpus as ic


@pytest.fixture(params=["decisions", "optional", "required"])
def reader(request):
    if request.param == "decisions":
        return ic.load_decisions_lock, "DECISIONS_LOCK_NAME", {}
    return ic.load_lock, "LOCK_NAME", ({"required": True}
                                      if request.param == "required" else {})


def test_json_values_and_duplicate_keys_survive(reader, tmp_path, capsys):
    load, constant, kwargs = reader
    path = tmp_path / getattr(ic, constant)
    for raw, expected in [
        (b"{}", {}),
        ('{"nested": {"text": "ä\\r\\n"}, "rows": [null, true, 1.5]}'.encode(),
         {"nested": {"text": "ä\r\n"}, "rows": [None, True, 1.5]}),
        (b'{"same": 1, "same": 2}', {"same": 2}),
    ]:
        path.write_bytes(raw)
        assert load(tmp_path, **kwargs) == expected
        assert path.read_bytes() == raw
    assert capsys.readouterr() == ("", "")


def test_absent_and_nonfile_locks_keep_required_behavior(reader, tmp_path):
    load, constant, kwargs = reader
    path = tmp_path / getattr(ic, constant)
    for shape in ("missing", "directory", "dangling_symlink"):
        if shape == "directory":
            path.mkdir()
        elif shape == "dangling_symlink":
            path.symlink_to(tmp_path / "missing-target")
        if kwargs.get("required"):
            with pytest.raises(ic.PipelineError) as caught:
                load(tmp_path, **kwargs)
            assert str(caught.value) == f"{path} missing — run the scaffold phase first"
            assert caught.value.__cause__ is caught.value.__context__ is None
            assert not caught.value.__suppress_context__
        else:
            first, second = load(tmp_path, **kwargs), load(tmp_path, **kwargs)
            assert first == second == {}
            assert first is not second
        if path.is_symlink():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    target = tmp_path / "target"
    target.write_text('{"linked": true}', encoding="utf-8")
    path.symlink_to(target)
    assert load(tmp_path, **kwargs) == {"linked": True}


def test_nonobject_failures_retain_ambient_exception_context(reader, tmp_path):
    load, constant, kwargs = reader
    path = tmp_path / getattr(ic, constant)
    for raw in ("[]", "null", '"value"', "1", "true"):
        path.write_text(raw, encoding="utf-8")
        try:
            raise RuntimeError("caller context")
        except RuntimeError as ambient:
            with pytest.raises(ic.PipelineError) as caught:
                load(tmp_path, **kwargs)
            assert str(caught.value) == f"{path} must hold a JSON object — re-run scaffold"
            assert caught.value.__cause__ is None
            assert caught.value.__context__ is ambient
            assert not caught.value.__suppress_context__


@pytest.mark.parametrize("raw", [b"", b"{broken", b"\xff", b"\xef\xbb\xbf{}"])
def test_decode_failures_chain_the_original_error(reader, tmp_path, raw):
    load, constant, kwargs = reader
    path = tmp_path / getattr(ic, constant)
    path.write_bytes(raw)
    with pytest.raises(ic.PipelineError) as caught:
        load(tmp_path, **kwargs)
    error = caught.value
    assert isinstance(error.__cause__, (UnicodeDecodeError, json.JSONDecodeError))
    assert error.__context__ is error.__cause__
    assert error.__suppress_context__
    assert str(error) == (f"{path} unreadable as JSON ({error.__cause__}) — a truncated or "
                          "merge-conflicted lock; restore it or re-run scaffold")
    assert path.read_bytes() == raw


@pytest.mark.parametrize("method,error,wrapped", [
    ("is_file", PermissionError("cannot stat"), False),
    ("read_text", PermissionError("cannot read"), True),
    ("read_text", FileNotFoundError("vanished after stat"), True),
    ("read_text", ValueError("unexpected read failure"), False),
    ("read_text", KeyboardInterrupt("interrupted"), False),
])
def test_io_failures_keep_their_boundary(reader, tmp_path, monkeypatch,
                                        method, error, wrapped):
    load, constant, kwargs = reader
    path = tmp_path / getattr(ic, constant)
    path.write_text("{}", encoding="utf-8")

    def fail(self, **options):
        assert self == path
        assert options == ({"encoding": "utf-8"} if method == "read_text" else {})
        raise error

    monkeypatch.setattr(Path, method, fail)
    with pytest.raises(ic.PipelineError if wrapped else type(error)) as caught:
        load(tmp_path, **kwargs)
    if wrapped:
        assert caught.value.__cause__ is caught.value.__context__ is error
        assert caught.value.__suppress_context__
        assert str(caught.value) == (
            f"{path} unreadable as JSON ({error}) — a truncated or "
            "merge-conflicted lock; restore it or re-run scaffold")
    else:
        assert caught.value is error


def test_names_decoder_and_error_class_are_resolved_at_call_time(
        reader, tmp_path, monkeypatch):
    load, constant, kwargs = reader
    path = tmp_path / "renamed.json"
    path.write_text("decoder input", encoding="utf-8")
    monkeypatch.setattr(ic, constant, path.name)
    received = []
    result = {"returned": True}

    def decode(text):
        received.append(text)
        return result

    decoder = SimpleNamespace(loads=decode, JSONDecodeError=json.JSONDecodeError)
    monkeypatch.setattr(ic, "json", decoder)
    assert load(tmp_path, **kwargs) is result
    assert received == ["decoder input"]

    class ReboundPipelineError(Exception):
        pass

    monkeypatch.setattr(ic, "PipelineError", ReboundPipelineError)
    injected = json.JSONDecodeError("injected", "{}", 1)

    def fail(text):
        raise injected

    decoder.loads = fail
    with pytest.raises(ReboundPipelineError) as caught:
        load(tmp_path, **kwargs)
    assert caught.value.__cause__ is caught.value.__context__ is injected
    assert caught.value.__suppress_context__


def test_reader_signatures_remain_public_contracts():
    assert str(inspect.signature(ic.load_decisions_lock)) == "(root: 'Path') -> 'dict'"
    assert str(inspect.signature(ic.load_lock)) == (
        "(root: 'Path', *, required: 'bool' = False) -> 'dict'")
