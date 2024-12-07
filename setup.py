"""Setup file for pip installs"""
from setuptools import setup, find_packages

with open("requirements.txt", encoding="utf-8") as f:
    requirements = f.read().splitlines()

setup(
    name='zse',
    version='1.1.0',
    description='A CLI tool that allows UNSW students to submit work to CSE machines.',
    author='Kareem Agha',
    packages=find_packages(),
    package_data={
        '': ['config.ini'],
    },
    include_package_data=True,
    py_modules=['main'],
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'zse=main:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.0',
)
