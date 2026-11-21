from setuptools import setup

setup(
    name="aiur_flight",
    version="0.1.0",
    packages=["aiur_flight"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/aiur_flight"]),
        ("share/aiur_flight", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    description="STRATO flight nodes: float manager, station keeper, termination, mission logger",
    license="Apache-2.0",
    entry_points={"console_scripts": ['float_manager = aiur_flight.float_manager:main', 'station_keeper = aiur_flight.station_keeper:main', 'termination = aiur_flight.termination:main', 'mission_logger = aiur_flight.mission_logger:main']},
)
