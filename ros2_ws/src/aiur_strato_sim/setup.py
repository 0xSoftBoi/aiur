from setuptools import setup

setup(
    name="aiur_strato_sim",
    version="0.1.0",
    packages=["aiur_strato_sim"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/aiur_strato_sim"]),
        ("share/aiur_strato_sim", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    description="Simulated STRATO vehicle behind standard ROS 2 topics",
    license="Apache-2.0",
    entry_points={"console_scripts": ['plant = aiur_strato_sim.plant_node:main', 'flight_plant = aiur_strato_sim.flight_plant_node:main']},
)
