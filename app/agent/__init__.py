"""Agent core: orchestrator.py (the OBSERVE->PLAN->ACT->OBSERVE->ANALYZE->
DECIDE->REPORT loop), planner.py (deterministic objective parsing, task
planning, and dynamic tool selection -- no network access needed),
llm_client.py (a genuine Claude tool-use agentic loop used instead of
planner.py when ANTHROPIC_API_KEY is configured), prompts.py (the LLM
system prompt), and state.py (the run-state object threaded through the
pipeline). Gap analysis and prioritization live in `app.compliance`, not
here."""
