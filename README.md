This project provides tools for systematic deployment for django projects 
in virtual environments. It depends on Fabric as underlying framework, 
ssh to connect to the hosts, wheels as package format, and pip to install 
and manage the packages.

The managing environment needs python 2.7, Fabric, paramiko, pip and 
typing. 

The managed environments can run under any c-python environment 
(tested is only 2.6 and 2.7) Other python interpreters might work,
but I have not tried to cope with wheel files for them.

The current status is pre-alpha. It works for me, but only my use cases
have been tested.


Motivation
==========

A problem I have often faced is that I have multiple virtual python 
environments with lots of packages that have to be kept in sync. 
Sometimes this need arises in strange internal networks that have no
reliable network connection to pypi, or for forked versions of packages
that are not available on pypi.

I wanted this tool to be straight forward and simple, and easy to adopt 
or fix. This project is the result.


Concepts
========

The basic operations are provided by fabric, and you need to write your 
own fabfile.py that includes the configuration of the virtual 
environments to manage. The sample_fabfile.py is a good start. 

See fabric on how to install fabric and make the fabfile available.

For management of the wheels, you need one directory that holds all the 
wheels ('wheels'), and a file that contains a log of all wheels 
available and the time of installation ('release_log').

Usage
=====

First, create an empty directory to hold the wheels.

Then you need the fabfile (see the sample) adopted to your configuration.

You also need a list of requirements for the virtual environments.
Currently the format is restricted. Permitted is either no restriction at all, e.g.:

    typing

or giving the exact version, like::

    typing==3.0.2

To inject a new package or update a package, you have to build a wheel first. 
This is outside of the scope of this tool, but if you have all dependencies 
installed, it's an easy command::

    pip wheel .

Afterwards you have to add it to the repository::

    fab add_wheel:filename

Or, to include a multitude::

    for i in *.whl; do; fab add_wheel:$i; done

When all required wheels are in place, you can start to push deployments:

    fab deploy

or

    fab deploy:name

The first option deploys to all known virtualenvs, the second compares 
the given name to the configured hosts and virtual environemnts. 
The following types of names are supported:

        - hostname
        - "vpy_user@host"
        - "user@host:full_path_to_vpy"
        - "host:full_path_vpy"
        - ":full_path"
        - "user@"

For each virtual environment, the packages to deploy will be presented 
to you, and then you can choose whether you want to deploy to this 
virtualenv or whether you want to skip it.


How deployment works
====================

The following steps are carried out:

- Read in the requirements
- Connect to the virtualenv and read the installed packages (by pip freeze)
- Find out which packages need to be installed
- Ask the user for confirmation
- Install the packages (by pip install --upgrade)
- Migrate the database (by django-admin migrate)
- Reload the web services (by the command configured in the fabfile)
