from setuptools import setup, find_packages

setup(
    name="processmanager",
    version="0.1.0",
    packages=find_packages(),         # now finds the processmanager/ folder
    install_requires=["appdirs"],
    entry_points={
        "console_scripts": [
            "schedulerctl = processmanager.cli:main",
        ],
    },
    include_package_data=True,
)
