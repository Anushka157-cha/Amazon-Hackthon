"""Tests for Alexa+ Voice Simulator CLI."""

import pytest
from unittest.mock import patch, MagicMock
from demo.alexa_sim import AlexaSimulator


@pytest.fixture
def sim():
    return AlexaSimulator(base_url="http://testserver")


def test_alexa_sim_dispatch_exit(sim):
    assert sim.dispatch("exit") is False
    assert sim.dispatch("quit") is False


def test_alexa_sim_dispatch_help(sim, capsys):
    assert sim.dispatch("help") is True
    out = capsys.readouterr().out
    assert "Supported Natural Phrases" in out


def test_alexa_sim_dispatch_diagnose(sim):
    with patch.object(sim, "handle_diagnose_and_propose") as mock_diag:
        assert sim.dispatch("what's wrong with my home") is True
        mock_diag.assert_called_once()


def test_alexa_sim_dispatch_approve(sim):
    with patch.object(sim, "handle_approve") as mock_appr:
        assert sim.dispatch("yes go ahead") is True
        mock_appr.assert_called_once_with(confirmed=True)


def test_alexa_sim_dispatch_reject(sim):
    with patch.object(sim, "handle_approve") as mock_appr:
        assert sim.dispatch("no don't do it") is True
        mock_appr.assert_called_once_with(confirmed=False)


def test_alexa_sim_dispatch_rollback(sim):
    with patch.object(sim, "handle_rollback") as mock_rb:
        assert sim.dispatch("undo that") is True
        mock_rb.assert_called_once()
