from setuptools import setup, find_packages

setup(
    name="agentguard-llm",
    version="0.1.0",
    description="Production-grade fault tolerance for AI agents — circuit breakers, LLM-aware retry, idempotency, and loop detection",
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
    ],
    keywords=[
        "ai agents", "llm", "fault tolerance", "circuit breaker",
        "retry", "idempotency", "agent reliability", "ai production",
        "langchain", "autogen", "crewai", "agent failure", "llm retry"
    ],
    project_urls={
        "Bug Reports": "https://github.com/agentguard-ai/agentguard/issues",
        "Source": "https://github.com/agentguard-ai/agentguard",
    },
)
