#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for openchecker.aksk.default_request.DefaultRequest.set_url()."""

from openchecker.aksk.default_request import DefaultRequest


def test_set_url_splits_query_string_from_path():
    """set_url() must keep the path clean and expose the query string as params."""
    request = DefaultRequest("my-access-id", "my-secret")
    request.set_url("https://api.example.com/v1/repos?state=all&page=2")

    assert request.get_path() == "https://api.example.com/v1/repos"
    assert request.get_query_params() == {"state": "all", "page": "2"}
    assert request.get_url() == "https://api.example.com/v1/repos?state=all&page=2"


def test_set_url_without_query_string_keeps_path():
    request = DefaultRequest("my-access-id", "my-secret")
    request.set_url("https://api.example.com/v1/repos")

    assert request.get_path() == "https://api.example.com/v1/repos"
    assert request.get_query_params() == {}


def test_set_url_does_not_treat_path_as_a_query_parameter():
    """The part before '?' is a path, not a key/value pair."""
    request = DefaultRequest("my-access-id", "my-secret")
    request.set_url("https://api.example.com/v1/repos?a=1")

    assert request.get_path() == "https://api.example.com/v1/repos"
    assert list(request.get_query_params()) == ["a"]
