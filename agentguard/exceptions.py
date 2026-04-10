class AgentGuardError(Exception):
    pass

class CircuitOpenError(AgentGuardError):
    pass

class MaxRetriesExceededError(AgentGuardError):
    pass

class IdempotencyError(AgentGuardError):
    pass

class AgentTimeoutError(AgentGuardError):
    pass
