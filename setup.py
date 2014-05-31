#!/usr/bin/env python

from setuptools import setup, find_packages


setup(name='ppreporter',
      version='0.1.0',
      description='A daemon that processes events from PowerPool(s) via a ZeroMQ bridge',
      author='Isaac Cook',
      author_email='isaac@simpload.com',
      url='http://www.python.org/sigs/distutils-sig/',
      packages=find_packages(),
      entry_points={
          'console_scripts': [
              'ppreporter = ppreporter.entry:main'
          ]
      }
      )
