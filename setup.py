#!/usr/bin/env python
import os
from setuptools import setup, find_packages


long_description = open(
    os.path.join(
        os.path.dirname(__file__),
        'README.md'
    )
).read()


setup(
    name='transient',
    author='Adam Schwalm',
    version='0.1',
    license='LICENSE',
    url='https://github.com/ALSchwalm/transient',
    description='A QEMU wrapper adding vagrant support and shared folders',
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages('.', exclude=["*.tests", "*.tests.*", "tests.*", "tests"]),
    install_requires=[
        "certifi==2020.4.5.1",
        "chardet==3.0.4",
        "idna==2.9",
        "importlib-resources==1.5.0",
        "requests==2.23.0",
        "urllib3==1.25.9"
    ],
    extras_require={
        "dev": [
            "autopep8==1.5.2",
            "mypy==0.770",
            "mypy-extensions==0.4.3",
            "pycodestyle==2.6.0",
            "typed-ast==1.4.1",
            "typing==3.7.4.1",
            "typing-extensions==3.7.4.2",
            "zipp==3.1.0"
        ],
    },
    entry_points={
        'console_scripts': [
            'transient = transient.cli:main',
        ]
    },
    package_data = {
        'transient': ['vagrant_keys/*'],
    },
    keywords=['qemu']
)
