from setuptools import setup
import os
from glob import glob

package_name = 'scara_solder_sim'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your_name',
    maintainer_email='you@example.com',
    description='CSV to SCARA joint-angle simulation (theta = 0)',
    license='MIT',
    entry_points={
        'console_scripts': [
            'solder_path_node = scara_solder_sim.solder_path_node:main',
        ],
    },
)
