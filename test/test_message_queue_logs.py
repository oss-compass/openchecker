#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for openchecker.message_queue.view_queue_logs()."""

import builtins
import io
import locale
import os
import sys

import pytest

from openchecker.message_queue import view_queue_logs

UTF8_ONLY_LINE = "Queue opencheck published \U0001F680\n"


def _write_log(tmp_path):
    path = tmp_path / "opencheck.log"
    path.write_bytes(UTF8_ONLY_LINE.encode("utf-8"))
    return str(path)


@pytest.mark.skipif(
    locale.getencoding().lower().replace("-", "") == "utf8",
    reason="default text encoding is already UTF-8, so the locale cannot show the bug",
)
def test_view_queue_logs_reads_utf8_file(tmp_path):
    """A UTF-8 log file must be read as UTF-8, whatever the host locale is."""
    path = _write_log(tmp_path)

    assert view_queue_logs(path) == [UTF8_ONLY_LINE]


def test_view_queue_logs_requests_utf8_from_open(tmp_path, monkeypatch):
    """The encoding must be explicit, so the behaviour is locale independent."""
    path = _write_log(tmp_path)
    seen = {}
    real_open = builtins.open

    def spy_open(file, mode="r", *args, **kwargs):
        if os.fspath(file) == path:
            seen["encoding"] = kwargs.get("encoding")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    view_queue_logs(path)

    assert seen.get("encoding") == "utf-8"
