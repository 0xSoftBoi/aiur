cmake_minimum_required(VERSION 3.8)
project(aiur_description)
find_package(ament_cmake REQUIRED)
install(DIRECTORY urdf meshes models worlds launch DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/gz_drag_check.py scripts/gz_fins_run.py scripts/gz_fins_check.py
        scripts/gz_fins_diagnose.py DESTINATION lib/${PROJECT_NAME})
ament_package()
