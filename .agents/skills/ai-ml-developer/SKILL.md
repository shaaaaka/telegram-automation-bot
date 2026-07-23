---
name: ai-ml-developer
description: Guidelines for building reliable LLM integrations, prompt engineering, agentic workflows, and managing OpenAI API calls efficiently.
---

# AI & LLM Integration Guidelines

Use this skill when developing or modifying LLM clients, prompt handlers, AI bot responses, or agentic automation workflows.

## Core Integration Rules

1. **Async & Resilience in LLM Calls**
   - Always use asynchronous client calls (`AsyncOpenAI` or similar async SDKs).
   - Wrap external LLM API calls in robust retry mechanisms (exponential backoff) to handle rate limits (`429`), timeouts, or temporary API outages (`5xx`).
   - Set strict connection and read timeouts on client instances to prevent blocking bot worker tasks.

2. **Prompt Engineering & Context Management**
   - Separate system prompts, instructions, and dynamic user inputs cleanly.
   - Use structured prompts with explicit system instructions, constraints, and output formatting rules.
   - Avoid sending excessive or redundant context in conversation history. Prune or summarize older messages to save tokens and avoid token limit truncation.

3. **Structured Outputs & Parsing**
   - Prefer JSON mode / structured outputs (`response_format={"type": "json_object"}` or Pydantic parsing) when LLMs generate structured data.
   - Always validate LLM responses with Pydantic or `try-except` parsing before applying changes to database or sending messages to end users.
   - Handle invalid or malformed LLM outputs gracefully with automatic fallback strategies.

4. **Streaming & Asynchronous Processing**
   - For long text generations, use streaming (`stream=True`) where applicable to lower perceived latency for Telegram users or Web clients.
   - For background or heavy AI operations, offload work to background tasks or queue handlers without blocking main event loops.

5. **Token Usage Monitoring & Cost Control**
   - Log token consumption (`prompt_tokens`, `completion_tokens`, `total_tokens`) for telemetry and billing tracking.
   - Use cost-efficient model tiers (e.g. `gpt-4o-mini` or `flash` variants) for repetitive/routine classification tasks, reserving larger models (`gpt-4o`/`pro`) for complex reasoning.
