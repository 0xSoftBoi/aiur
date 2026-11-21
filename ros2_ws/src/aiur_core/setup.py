from setuptools import find_packages, setup

setup(
    name="aiur_core",
    version="0.1.0",
    packages=find_packages(include=["aiur", "aiur.*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/aiur_core"]),
        ("share/aiur_core", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    description="aiur models and flight-software candidates",
    license="Apache-2.0",
)
