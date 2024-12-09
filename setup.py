"""Setup file for pip installs"""
from setuptools import setup, find_packages
from setuptools.command.install import install

class PostInstallCommand(install):
    """Prints message after install"""
    def run(self):
        install.run(self)
        print("\033[1;32mThank you for installing \033[1;33mzse\033[0m!")
        print("You will need to configure your settings."
              + "A config.ini file will be created when you first run zse")

setup(
    name='zse',
    version='1.1.4',
    description='A CLI tool that allows UNSW students to submit work to CSE machines.',
    author='Kareem Agha',
    packages=find_packages(),
    package_data={
        '': ['config.ini'],
    },
    include_package_data=True,
    py_modules=['main'],
    install_requires=[
        'paramiko',
        'colorama',
        'platformdirs',
        'setuptools',
    ],
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
