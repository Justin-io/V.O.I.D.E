"""Unit Tests for PolicyEngine."""

from voide.agent.policy.policy_engine import PolicyEngine, RiskTier


def test_low_risk_tools():
    policy = PolicyEngine("/workspace")
    dec = policy.evaluate("read_file", {"path": "main.py"})
    assert dec.allowed is True
    assert dec.risk_tier == RiskTier.LOW
    assert dec.requires_approval is False


def test_dangerous_commands_gated():
    policy = PolicyEngine("/workspace")
    
    # Sudo blocked
    d1 = policy.evaluate("terminal_write", {"command": "sudo rm -rf /var"})
    assert d1.allowed is False
    assert d1.risk_tier == RiskTier.HIGH
    assert d1.requires_approval is True

    # Fork bomb blocked
    d2 = policy.evaluate("terminal_write", {"command": ":(){ :|:& };:"})
    assert d2.allowed is False
    assert d2.risk_tier == RiskTier.HIGH


def test_sensitive_path_protection():
    policy = PolicyEngine("/workspace")
    
    d1 = policy.evaluate("write_file", {"path": ".git/config", "content": ""})
    assert d1.allowed is False
    assert d1.risk_tier == RiskTier.HIGH
    assert d1.requires_approval is True

    d2 = policy.evaluate("write_file", {"path": ".env.production", "content": "SECRET=1"})
    assert d2.allowed is False
    assert d2.risk_tier == RiskTier.HIGH


def test_unknown_tool_rejection():
    policy = PolicyEngine("/workspace")
    dec = policy.evaluate("arbitrary_exec", {"foo": "bar"})
    assert dec.allowed is False
    assert dec.risk_tier == RiskTier.HIGH
    assert dec.requires_approval is True
