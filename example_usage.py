"""
agentguard — Example Usage
"""
from agentguard import GuardedAgent, CircuitBreaker, llm_retry, FailureType

# 1. GuardedAgent — full protection wrapper
agent = GuardedAgent(
    name="my_llm_agent",
    max_retries=3,
    circuit_threshold=5,
    timeout=30.0,
    loop_detection=True,
    max_repeated_actions=3,
)

def call_llm(prompt: str) -> str:
    # Replace with your actual LLM call
    return f"Response to: {prompt}"

result = agent.run(call_llm, "What is the capital of France?", action_label="llm_call")
print(result)
print(agent.get_stats())

# 2. Circuit Breaker standalone
cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0, name="openai")
try:
    response = cb.call(call_llm, "Hello")
except Exception as e:
    print(f"Protected: {e}")

# 3. Decorator-style retry
@llm_retry(max_attempts=3)
def my_agent_step(query: str) -> str:
    return call_llm(query)

print(my_agent_step("Tell me a joke"))
