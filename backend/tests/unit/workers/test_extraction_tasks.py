"""Unit tests for file extraction task behavior."""

import uuid
from types import SimpleNamespace

import pytest

from app.models.uploaded_file import FileStatus
from app.workers.tasks import extraction_tasks


class _FakeAsyncSession:
    def __init__(self, record):
        self.record = record
        self.commit_snapshots: list[tuple[FileStatus, str | None, str | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, model, file_id):
        return self.record

    async def commit(self):
        self.commit_snapshots.append(
            (
                self.record.status,
                self.record.error_message,
                self.record.extracted_text,
            )
        )


def _factory_for(record, sessions: list[_FakeAsyncSession]):
    def factory():
        session = _FakeAsyncSession(record)
        sessions.append(session)
        return session

    return factory


def test_extract_text_from_txt_bytes() -> None:
    result = extraction_tasks._extract_text_from_bytes("text/plain", b"hello world")
    assert result == "hello world"


def test_extract_text_from_pdf_uses_pypdf(monkeypatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class FakeReader:
        def __init__(self, _fileobj) -> None:
            self.pages = [FakePage("Page One"), FakePage("Page Two")]

    monkeypatch.setattr(extraction_tasks, "PdfReader", FakeReader)

    result = extraction_tasks._extract_text_from_bytes("application/pdf", b"%PDF-1.4")

    assert result == "Page One\nPage Two"


def test_extract_text_from_docx_uses_python_docx(monkeypatch) -> None:
    class FakeDocument:
        def __init__(self, _fileobj) -> None:
            self.paragraphs = [
                SimpleNamespace(text="First paragraph"),
                SimpleNamespace(text=""),
                SimpleNamespace(text="Second paragraph"),
            ]

    monkeypatch.setattr(extraction_tasks, "Document", FakeDocument)

    result = extraction_tasks._extract_text_from_bytes(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"docx-bytes",
    )

    assert result == "First paragraph\nSecond paragraph"


@pytest.mark.asyncio
async def test_extract_file_text_async_marks_processing_then_ready() -> None:
    file_id = uuid.uuid4()
    record = SimpleNamespace(
        id=file_id,
        storage_key="owner/file.pdf",
        content_type="text/plain",
        status=FileStatus.pending,
        error_message="old error",
        extracted_text=None,
    )
    sessions: list[_FakeAsyncSession] = []

    result = await extraction_tasks._extract_file_text_async(
        file_id,
        session_factory=_factory_for(record, sessions),
        downloader=lambda storage_key: b"hello extracted text",
        extractor=lambda content_type, data: data.decode("utf-8"),
    )

    assert result == {
        "file_id": str(file_id),
        "status": "ready",
        "chars_extracted": len("hello extracted text"),
    }
    assert record.status == FileStatus.ready
    assert record.error_message is None
    assert record.extracted_text == "hello extracted text"
    assert sessions[0].commit_snapshots == [
        (FileStatus.processing, None, None),
        (FileStatus.ready, None, "hello extracted text"),
    ]


@pytest.mark.asyncio
async def test_set_file_error_persists_error_state() -> None:
    file_id = uuid.uuid4()
    record = SimpleNamespace(
        id=file_id,
        storage_key="owner/file.pdf",
        content_type="text/plain",
        status=FileStatus.processing,
        error_message=None,
        extracted_text="partial",
    )
    sessions: list[_FakeAsyncSession] = []

    await extraction_tasks._set_file_error(
        file_id,
        "boom",
        session_factory=_factory_for(record, sessions),
    )

    assert record.status == FileStatus.error
    assert record.error_message == "boom"
    assert sessions[0].commit_snapshots == [(FileStatus.error, "boom", "partial")]


def test_extract_file_text_retries_transient_errors(monkeypatch) -> None:
    file_id = str(uuid.uuid4())
    retry_calls: list[Exception] = []
    retry_exc = RuntimeError("retry scheduled")

    def fake_asyncio_run(coro):
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        raise RuntimeError("temporary storage failure")

    monkeypatch.setattr(extraction_tasks.asyncio, "run", fake_asyncio_run)

    task = SimpleNamespace(
        request=SimpleNamespace(retries=0),
        max_retries=3,
        retry=lambda exc: retry_calls.append(exc) or (_ for _ in ()).throw(retry_exc),
    )

    with pytest.raises(RuntimeError, match="retry scheduled"):
        extraction_tasks.extract_file_text.run.__func__(task, file_id)

    assert len(retry_calls) == 1
    assert "temporary storage failure" in str(retry_calls[0])


def test_extract_file_text_marks_error_after_final_retry(monkeypatch) -> None:
    file_id = uuid.uuid4()
    error_runs: list[tuple[uuid.UUID, str]] = []

    def fake_asyncio_run(arg):
        if isinstance(arg, SimpleNamespace) and getattr(arg, "kind", "") == "error":
            error_runs.append((arg.file_id, arg.message))
            return None
        close = getattr(arg, "close", None)
        if close is not None:
            close()
        raise RuntimeError("permanent failure")

    monkeypatch.setattr(extraction_tasks.asyncio, "run", fake_asyncio_run)
    monkeypatch.setattr(
        extraction_tasks,
        "_set_file_error",
        lambda fid, msg: SimpleNamespace(kind="error", file_id=fid, message=msg),
    )

    task = SimpleNamespace(
        request=SimpleNamespace(retries=3),
        max_retries=3,
        retry=lambda exc: None,
    )

    result = extraction_tasks.extract_file_text.run.__func__(task, str(file_id))

    assert result == {"file_id": str(file_id), "status": "error", "chars_extracted": 0}
    assert error_runs == [(file_id, "permanent failure")]
