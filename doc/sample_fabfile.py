# -*- coding: utf-8 -*-

"""
This is how your fabfile could look like. It's just python and you can use everything the language offers.

The sample configuration defines one staging host ('staging') with one virtualenv for one project
and 10 prod hosts ('prod0' ... 'prod9') with one virtualenv for one project each.

The wheel files are held in /somewhere/wheels, the release log in /somewhere/releases.log
"""

from __future__ import unicode_literals
from django_fabdeploy import *

requirements = read_requirements('/somewhere/requirements.txt')


def reload_cmd(virtualenv_conf):
    # type: (VirtualenvConf) -> unicode
    """
    This returns the command line to reload the webserver after deploying changes.
    If you set HostConf.reload_once to True, it will be called only once for each host,
    else it will be called for each virtualenv.

    :param virtualenv_conf: For which virtualenv it needs to be executed.
    """
    return 'systemctl reload apache2'


my_config = LocalConf(
    wheels='/somewhere/wheels',
    release_log = ReleaseLog('/somewhere/releases.log'),
    hosts = [
        # staging host
        HostConf(
            hostname = 'staging',
            reload_cmd=reload_cmd,
            reload_once=True,
            vpys = [
                VirtualenvConf(
                    ssh_user = 'yoda',
                    vpy_path = '/var/lib/myvirtualenv',
                    vpy_user = 'yoda',
                    requirements = requirements,
                    custom_packages=['staging_site'],
                    projects = [
                        ProjectConf(settings_module='staging_settings', user='wwwyoda', migrate=True)
                    ]
                )
            ]
        )
    ]
    +
    # prod hosts
    [
        HostConf(
            hostname = 'www%d' % i,
            reload_cmd=reload_cmd,
            reload_once=True,
            vpys = [
                VirtualenvConf(
                    ssh_user='admin',
                    vpy_path='/var/lib/myvirtualenv',
                    vpy_user='yoda',
                    requirements=requirements,
                    custom_packages=['prod_settings'],
                    projects = [ProjectConf(settings_module='staging_settings', user='wwwyoda', migrate=True)]
                )
            ]
        )
        for i in range(10)
    ]
)


# The following functions define the fabric tasks.
# django_fabdeploy contains these ready to use, but you
# need to fill in your configuration.
# There should be a better way ...

def deploy(vpy_names=""):
    return my_config.task_deploy(vpy_names)

def add_wheel(path):
    return my_config.task_add_wheel(path)
