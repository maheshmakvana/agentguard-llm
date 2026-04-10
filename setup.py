from setuptools import setup, find_packages

setup(
    name="agentguard-llm",
    version="0.2.0",
    description=(
        "Production-grade fault tolerance for AI agents — circuit breakers, LLM-aware retry, "
        "idempotency, loop detection, fallback chains, async support, health monitoring, and "
        "budget enforcement for LangChain, AutoGen, CrewAI, and any LLM pipeline"
    ),
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="AgentGuard Contributors",
    url="https://github.com/agentguard-ai/agentguard",
    packages=find_packages(exclude=["tests*", "venv*"]),
    python_requires=">=3.8",
    install_requires=[],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: System :: Monitoring",
    ],
    keywords=[
        "ai agents", "llm", "fault tolerance", "circuit breaker",
        "retry", "idempotency", "agent reliability", "ai production",
        "langchain", "autogen", "crewai", "agent failure", "llm retry",
        "llm fallback", "agent health", "llm budget", "agent guard",
        "llm circuit breaker", "ai resilience", "production ai", "llm timeout",
        "ai agent monitoring", "llm observability", "async agent", "agent decorator",
        "ai fault injection", "llm error handling", "agent loop detection",
        "ai agent framework", "llm rate limit", "ai production ready",
    ],
    project_urls={
        "Bug Reports": "https://github.com/agentguard-ai/agentguard/issues",
        "Source": "https://github.com/agentguard-ai/agentguard",
    },
)
