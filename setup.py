#!/usr/bin/env python

"""The setup script."""

from setuptools import setup, find_packages

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('HISTORY.md') as history_file:
    history = history_file.read()

requirements = ["skypilot[all]>=0.4.1",
                "opentelemetry-api>=1.22.0",
                "opentelemetry-exporter-otlp>=1.22",
                "opentelemetry-instrumentation",
                "opentelemetry-sdk>=1.22.0",
                "fastapi>=0.110.0",
                "opentelemetry-instrumentation-fastapi>=0.40.0",
                'uvicorn>=0.23.0',
                'fire>=0.4.0',
                ]

test_requirements = ['pytest>=3', ]

setup(
    author="Antti Puurula, Anil Gurbuz",
    python_requires='>=3.7, <3.12',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    description="Open-source Sky Computing Inference Endpoint",
    install_requires=requirements,
    license="Apache Software License 2.0",
    long_description=readme,
    long_description_content_type="text/markdown",
    include_package_data=True,
    keywords='flockserve',
    name='flockserve',
    packages=find_packages(include=['flockserve', 'flockserve.*']),
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/jdoodle-dev/flockserve',
    version='0.1.7',
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'flockserve = flockserve.cli:main',
        ],
    },
)
