from setuptools import find_packages, setup

package_name = 'pidog_behavior'

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
    description='PiDog behaviors: ball follower and VLM command planner',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'ball_follower_node = pidog_behavior.ball_follower_node:main',
            'vla_planner_node = pidog_behavior.vla_planner_node:main',
        ],
    },
)
