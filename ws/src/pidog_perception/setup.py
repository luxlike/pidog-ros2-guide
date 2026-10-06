from setuptools import find_packages, setup

package_name = 'pidog_perception'

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
    description='PiDog camera and color ball detection',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'camera_node = pidog_perception.camera_node:main',
            'ball_tracker_node = pidog_perception.ball_tracker_node:main',
        ],
    },
)
