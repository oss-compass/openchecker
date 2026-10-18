#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for openchecker.aksk.signer.Signer."""

from openchecker.aksk.default_request import DefaultRequest
from openchecker.aksk.signer import Signer


def _signed_request():
    request = DefaultRequest("my-access-id", "my-secret")
    request.set_method("GET")
    request.set_url("https://api.example.com/v1/repos")
    return request, Signer.sign(request)


def test_authorization_header_carries_the_access_id():
    _, authorization = _signed_request()

    assert "accessId=my-access-id" in authorization


def test_get_access_id_parses_the_header_it_produced():
    """Round-trip: the parser must read back what build_authorization_header wrote."""
    _, authorization = _signed_request()

    assert Signer.get_access_id(authorization) == "my-access-id"


def test_get_timestamp_parses_the_header_it_produced():
    request, authorization = _signed_request()
    request.set_timestamp("1700000000000")
    authorization = Signer.sign(request)

    assert Signer.get_timestamp(authorization) == 1700000000000
