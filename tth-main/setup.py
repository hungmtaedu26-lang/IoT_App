from setuptools import setup, find_packages

setup(
    name="zkp-snark-ver",
    version="0.1.0",
    packages=find_packages(include=["shared", "shared.*", "services", "services.*"]),
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.109",
        "uvicorn[standard]>=0.23",
        "requests>=2.31",
        "pydantic>=2.5",
        "python-dotenv>=1.0",
        "watchfiles>=0.21",
    ],
)