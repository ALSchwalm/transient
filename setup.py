#!/usr/bin/env python
import os
import re
from setuptools import setup, find_packages


long_description = open(
    os.path.join(
        os.path.dirname(__file__),
        'README.md'
    )
).read()

with open("transient/__init__.py", encoding="utf8") as f:
    version = re.search(r'__version__ = "(.*?)"', f.read()).group(1)

setup(
    name='transient',
    author='Adam Schwalm',
    version=version,
    license='LICENSE',
    url='https://github.com/ALSchwalm/transient',
    description='A QEMU wrapper adding vagrant support and shared folders',
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages('.', exclude=["*.tests", "*.tests.*", "tests.*", "tests"]),
    install_requires=[
        "beautifultable==0.8.0",
        "click==7.1.2",
        "importlib-resources==1.5.0",
        "progressbar2==3.51.3",
        "requests==2.23.0",
        "python-magic==0.4.18"
    ],
    extras_require={
        "dev": [
            "black==19.10b0",
            "mkdocs==1.1.2",
            "mypy==0.770",
            "PyHamcrest==2.0.2",
            "typing==3.7.4.1",
            "behave==1.2.6",
            "twine==3.1.1"
        ],
    },
    entry_points={
        'console_scripts': [
            'transient = transient.cli:main',
        ]
    },
    package_data = {
        'transient': ['static/*'],
    },
    keywords=['qemu']
)
