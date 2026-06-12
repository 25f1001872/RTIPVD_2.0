"""
RTIPVD — Setup Script
Backup setup.py for compatibility with older pip versions.
The primary config is in pyproject.toml.
"""

from setuptools import setup, find_packages

setup(
    name="rtipvd",
    version="1.0.0",
    packages=find_packages(include=["src*", "config*"]),
)