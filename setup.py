# -*- coding: utf-8 -*-

from distutils.core import setup

__VERSION__ = '0.1'
setup(
    name='django-fabdeploy',
    version=__VERSION__,
    long_description="""This project provides tools for systematic deployment for django projects
in virtual environments. It depends on Fabric as underlying framework,
ssh to connect to the hosts, wheels as package format, and pip to install and manage the packages.""",
    description='Systematic Deployment of Django Projects to Virtualenvs Using Fabric',
    url='https://github.com/mradziej/django_fabdeploy',
    author='Michael Radziej',
    author_email='mir@github.m1.spieleck.de',
    license='MIT',
    py_modules=['django_fabdeploy'],
    package_dir={'': 'src'},
    zip_safe=True,
    data_files=[('share/doc/django_fabdeploy', ['doc/sample_fabfile.py', 'README.md', 'LICENSE'])],
    install_requires=['Fabric', 'typing', 'pip'],
    keywords=['django', 'fabric', 'deployment', 'distribution'],
    classifiers=[
        'Development Stauts :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: Unix',
        'Programming Language :: Python :: 2.7',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Software Distribution',
    ],
)
