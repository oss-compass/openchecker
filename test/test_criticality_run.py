#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the vendored criticality-score ``run.py``.

``openchecker/criticality/run.py`` is a drop-in replacement for the
``criticality_score`` console script: the Dockerfile copies it over
``site-packages/criticality_score/run.py``.  It therefore keeps the
package-relative ``defaults`` import and the optional PyGithub / python-gitlab
imports of the upstream project.

The helpers below rebuild that minimal package layout in memory before loading
the module.  Keeping the layout local makes the tests hermetic: they never touch
an installed ``criticality_score`` distribution and they do not need a network
connection.
"""

import importlib.util
import os
import re
import sys
import types
import unittest
import warnings
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
_RUN_PATH = os.path.join(_PROJECT_ROOT, "openchecker", "criticality", "run.py")

# Minimal stand-in for ``criticality_score/defaults.py``.  run.py only resolves
# these names while a signal is evaluated, so the tests provide just the subset
# they exercise.
_DEFAULTS = {
    "FAIL_RETRIES": 3,
    "RELEASE_LOOKBACK_DAYS": 365,
    "ISSUE_LOOKBACK_DAYS": 365,
    "TOP_CONTRIBUTOR_COUNT": 100,
    # ``dependents_count`` scrapes GitHub's search page; the fake response used
    # below contains a single comma separated number.
    "DEPENDENTS_REGEX": re.compile(br"([\d,]+)"),
}


def _ensure_importable(name):
    """Make ``name`` importable, faking it when it is not installed.

    PyGithub, python-gitlab and pytz are optional while testing: run.py only
    needs the module objects to exist because the tests never reach the code
    paths that call them.
    """
    if name in sys.modules:
        return
    try:
        importlib.import_module(name)
    except ImportError:
        stub = types.ModuleType(name)
        stub.__path__ = []
        sys.modules[name] = stub


def _load_run_module():
    """Import ``openchecker/criticality/run.py`` as ``criticality_score.run``.

    The module lives inside the ``criticality_score`` distribution at runtime,
    so it cannot be imported as a regular ``openchecker`` submodule.  Recreate
    just enough of that package (``defaults`` plus the optional clients) to run
    it under the name it expects.
    """
    if "criticality_score.run" in sys.modules:
        return sys.modules["criticality_score.run"]

    for dependency in ("github", "gitlab", "pytz"):
        _ensure_importable(dependency)

    package = types.ModuleType("criticality_score")
    package.__path__ = []
    sys.modules["criticality_score"] = package

    defaults = types.ModuleType("criticality_score.defaults")
    for name, value in _DEFAULTS.items():
        setattr(defaults, name, value)
    sys.modules["criticality_score.defaults"] = defaults
    package.defaults = defaults

    spec = importlib.util.spec_from_file_location(
        "criticality_score.run", _RUN_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["criticality_score.run"] = module
    with warnings.catch_warnings():
        # run.py emits a DeprecationWarning while it is imported and the pytest
        # configuration promotes warnings to errors, so silence it here.
        warnings.simplefilter("ignore")
        spec.loader.exec_module(module)
    return module


run = _load_run_module()

# ``name``, ``url`` and ``language`` are metadata, ``last_commit`` guards the
# whole collection, and the remaining entries are the scored signals.
_METADATA_SIGNALS = {"name", "url", "language", "last_commit"}
_ABSTRACT_SIGNALS = (set(run.PARAMS) - {"dependents_count"}) | _METADATA_SIGNALS


def make_repository(fail_signal=None, **overrides):
    """Build a concrete ``Repository`` whose signals return constants.

    ``fail_signal`` turns a single signal into one that raises
    ``NotImplementedError``, reproducing a host platform that forgot to provide
    a signal.
    """
    values = {
        "name": "example",
        "url": "https://example.com/example/repo",
        "language": "python",
        "description": "example repository",
        "last_commit": object(),
        "created_since": 12,
        "updated_since": 1,
        "contributor_count": 3,
        "watchers_count": 7,
        "org_count": 1,
        "commit_frequency": 4.0,
        "recent_releases_count": 2,
        "updated_issues_count": 5,
        "closed_issues_count": 4,
        "comment_frequency": 1.5,
        "dependents_count": 0,
    }
    values.update(overrides)

    namespace = {}
    for signal, value in values.items():
        if signal == fail_signal:
            def _raise(self, _signal=signal):
                raise NotImplementedError(
                    f"{_signal} signal is not implemented")
            namespace[signal] = property(_raise)
        else:
            namespace[signal] = property(lambda self, _value=value: _value)

    # ``type`` is used instead of a class statement so the ABC metaclass sees
    # every property while it computes ``__abstractmethods__``.
    return type("_StubRepository", (run.Repository,), namespace)(object())


class TestRepositoryAbstractContract(unittest.TestCase):
    """The base class must reject hosts that miss part of the contract."""

    def test_repository_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            run.Repository(object())

    def test_every_required_signal_is_abstract(self):
        self.assertEqual(run.Repository.__abstractmethods__, _ABSTRACT_SIGNALS)

    def test_incomplete_subclass_is_rejected(self):
        class _IncompleteRepository(run.Repository):
            pass

        with self.assertRaises(TypeError) as ctx:
            _IncompleteRepository(object())

        message = str(ctx.exception)
        self.assertIn("description", message)
        self.assertIn("watchers_count", message)

    def test_base_properties_name_the_missing_signal(self):
        repository = make_repository()
        for signal in sorted(run.Repository.__abstractmethods__):
            descriptor = run.Repository.__dict__[signal]
            with self.assertRaises(NotImplementedError) as ctx:
                descriptor.fget(repository)
            self.assertIn(signal, str(ctx.exception))


class TestGetRepositoryStats(unittest.TestCase):
    """Signal collection must stay ordered and must not hide failures."""

    def test_stats_preserve_declared_order(self):
        stats = run.get_repository_stats(make_repository())
        self.assertEqual(list(stats)[:3], ["name", "url", "language"])
        self.assertEqual(list(stats)[3:], list(run.PARAMS))

    def test_empty_repository_returns_none(self):
        self.assertIsNone(
            run.get_repository_stats(make_repository(last_commit=None)))

    def test_failing_signal_is_raised_instead_of_a_key_error(self):
        repository = make_repository(fail_signal="description")
        with self.assertRaises(NotImplementedError) as ctx:
            run.get_repository_stats(repository)
        self.assertIn("description", str(ctx.exception))


class _StubCollection:
    """Stand-in for python-gitlab's lazy list objects (``project.commits``)."""

    def __init__(self, items):
        self._items = items

    def list(self, **kwargs):
        return list(self._items)


class _StubGitLabCommit:
    def __init__(self, created_at):
        self.created_at = created_at


class _StubNotes:
    def __init__(self, total):
        self.total = total


class _StubIssue:
    def __init__(self, total):
        self.notes = types.SimpleNamespace(
            list=lambda as_list=False: _StubNotes(total))


class _StubIssuesStatistics:
    def __init__(self, counts):
        self._counts = counts

    def get(self, **kwargs):
        return types.SimpleNamespace(
            statistics={"counts": dict(self._counts)})


class _StubGitLabProject:
    """Just enough of a python-gitlab ``Project`` for the signal lookups."""

    def __init__(self):
        self.name = "demo-project"
        self.web_url = "https://gitlab.com/example/demo-project"
        self.description = "Demo project used by the criticality tests"
        self.star_count = 42
        self.created_at = "2020-01-01T00:00:00.000000+0000"
        self.commits = _StubCollection(
            [_StubGitLabCommit("2024-01-01T00:00:00.000000+0000")])
        self.releases = _StubCollection([])
        self.tags = _StubCollection([])
        self.issues = _StubCollection([_StubIssue(3)])
        self.issuesstatistics = _StubIssuesStatistics({"all": 5, "closed": 4})

    def languages(self):
        return {"Python": 100.0}

    def repository_contributors(self, all=False):
        return [object(), object()]


class _StubResponse:
    status_code = 200
    content = b"1,234"


class TestGitLabRepository(unittest.TestCase):
    """GitLab must provide every signal; two of them used to be missing."""

    def test_gitlab_repository_implements_every_platform_signal(self):
        self.assertEqual(run.GitLabRepository.__abstractmethods__, frozenset())
        for signal in set(run.PARAMS) - {"dependents_count"}:
            self.assertIn(signal, vars(run.GitLabRepository))

    def test_gitlab_description_is_exposed(self):
        repository = run.GitLabRepository(_StubGitLabProject())
        self.assertEqual(
            repository.description,
            "Demo project used by the criticality tests")

    def test_gitlab_watchers_count_maps_to_stars(self):
        repository = run.GitLabRepository(_StubGitLabProject())
        self.assertEqual(repository.watchers_count, 42)

    def test_gitlab_stats_can_be_collected_end_to_end(self):
        repository = run.GitLabRepository(_StubGitLabProject())
        with mock.patch.object(run.requests, "get",
                               return_value=_StubResponse()):
            stats = run.get_repository_stats(repository)

        self.assertEqual(
            stats["description"],
            "Demo project used by the criticality tests")
        self.assertEqual(stats["watchers_count"], 42)
        self.assertEqual(stats["dependents_count"], 1234)
        for param in run.PARAMS:
            self.assertIn(param, stats)


if __name__ == "__main__":
    unittest.main()
