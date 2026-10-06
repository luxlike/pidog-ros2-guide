from setuptools import find_packages, setup

package_name = 'pidog_driver'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pidog',
    maintainer_email='pidog@example.com',
    description='ROS 2 hardware driver for SunFounder PiDog',
    license='MIT',
    entry_points={
        'console_scripts': [
            'imu_node = pidog_driver.imu_node:main',
            'driver_node = pidog_driver.driver_node:main',
        ],
    },
)
