"""Tests for core/agent_context.py."""

from core.agent_context import generate_agent_context
from core.fileio import read_json


def test_generate_agent_context(workspace):
    context = generate_agent_context(workspace)
    assert "generatedAt" in context
    assert "analytics" in context
    assert "topUrgentTasks" in context
    assert "weeklyBudgetStatus" in context
    assert "suggestions" in context

    # Should be written to file
    data = read_json(workspace / "planner" / "agent_context.json")
    assert data["analytics"]["streak"] == 3


def test_agent_context_has_budget_status(workspace):
    context = generate_agent_context(workspace)
    budgets = context["weeklyBudgetStatus"]
    assert len(budgets) >= 1
    assert budgets[0]["task_id"] == "important-project"
    assert budgets[0]["target_hours"] == 8
