from glob import glob

from setuptools import find_packages, setup

package_name = 'pidog_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pidog',
    maintainer_email='pidog@example.com',
    description='PiDog bringup launch files',
    license='MIT',
    entry_points={'console_scripts': []},
)
