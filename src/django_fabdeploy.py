# -*- coding: utf-8 -*-

from __future__ import absolute_import, unicode_literals, print_function, division
__all__ = ('HostConf', 'ProjectConf', 'VirtualenvConf', 'LocalConf', 'ReleaseLog', 'read_requirements')

import os
from distutils.version import LooseVersion

import datetime
from shutil import copy

import fabric, fabric.utils
from fabric.context_managers import cd, shell_env
from fabric.operations import put, prompt, warn
# noinspection PyCompatibility
from typing import NamedTuple, List, Dict, Iterable, Optional, Callable, Tuple
from os.path import basename


class Skip(Exception):
    pass


class PkgSpec(object):
    """
    A package with a specified version and a wheel file
    """
    def __init__(self, pkg, version, wheel):
        # type: (unicode, unicode, unicode) -> None
        self.pkg = pkg
        self.version = LooseVersion(version)
        self.wheel = wheel

    def __unicode__(self):
        return "%s==%s" % (self.pkg, self.version)


# Version information for a virtualenv
PyVersionInfo = NamedTuple('PyVersionInfo', [('major', int), ('minor', int)])


def get_platform_tags(wheel):
    # type (unicode) -> List[unicode]
    """
    Returns the python platform tags indicated by the file name.
    :param wheel: wheel file name (without directory)
    :return:
    """
    from pip.wheel import Wheel
    w = Wheel(wheel)
    return w.pyversions


class PkgSpecList(object):
    """
    A package in a certain release with matching wheels.
    """
    def __init__(self, pkg, version, wheels):
        # type: (unicode, unicode, List[unicode]) -> None
        self.pkg = pkg
        self.version = LooseVersion(version)
        self.wheels = [(get_platform_tags(w), w) for w in wheels]  # type: Tuple[List[unicode], unicode]

    def __unicode__(self):
        return "%s==%s (%s)" % (self.pkg, self.version, ", ".join("%s %s" % (v,w) for w,v in self.wheels))

    def __repr__(self):
        return b"<PkgSpecList %s>" % unicode(self).encode("utf-8")

    def get_wheel(self, py_versioninfo):
        # type: (PyVersionInfo) -> Optional[unicode]
        """
        Returns the wheel that matches the given platform best.
        :param py_versioninfo: python version (as from sys.version()
        :return: file name of the wheel
        """
        major, minor = py_versioninfo.major, py_versioninfo.minor
        for vs, w in self.wheels:
            for v in vs:
                if v[-2].isdigit():
                    if int(v[-2]) == major and int(v[-1]) == minor:
                        return w
        for vs, w in self.wheels:
            for v in vs:
                if not v[-2].isdigit() and (major==2 and v[-1] == '2' or major==3 and v[-1] == '3'):
                    return w
        return None

    def add_wheel(self, wheel):
        # type: (unicode) -> None
        """
        Adds a new wheel to this PkgSpecList.
        Does not check if it matches the version or whether it is already in the list.
        :param wheel:
        :return:
        """
        # noinspection PyUnresolvedReferences
        self.wheels.append((get_platform_tags(wheel), wheel))


ToInstallResult = NamedTuple("ToInstallResult", [
    ('installables', List[unicode]),
    ('missing', List[unicode]),
    ('ahead', List[PkgSpec]),
])


def read_requirements(path):
    # type: (unicode) -> Dict[unicode, LooseVersion]
    """
    Reads a simplified requirement list and returns it as package - version tuples.
    :param path: path to a requirement file

    Only the following types of version restrictions can be parsed:
    - no rectriction
    - restriction to a certain version (==...)
    """
    with open(path, "r") as f:
        return _lines_to_requirements(l.decode('utf-8') for l in f)


def _lines_to_requirements(lines):
    # type: (Iterable[unicode]) -> Dict[unicode, Optional[LooseVersion]]
    """
    Parses simplified requirement lines
    :param lines:
    :return:
    """
    pkgs = (l.strip().split("==", 1) for l in lines)
    return dict((x[0], LooseVersion(x[1]) if len(x)==2 else None) for x in pkgs)


class ProjectConf(object):
    """
    Configuration of a django project
    """
    def __init__(self, settings_module, user, migrate=True):
        # type: (unicode, Optional[unicode], bool) -> None
        self.settings_module = settings_module
        self.user = user
        # self.vpy will be set by VirtualenvConf.__init__()
        self.vpy = None  # type: VirtualenvConf
        self.migrate = migrate

    def __unicode__(self):
        return self.settings_module

    def settings(self, *args, **kwargs):
        """
        context manager like fabric's settings, initialized to deal with this project.
        :param args: see fabric
        :param kwargs: see fabric
        """
        defaults = {}
        if self.user != self.vpy.vpy_user:
            defaults = dict(sudo_user=self.user)
        defaults.update(kwargs)
        newargs = (shell_env(DJANGO_SETTINGS_MODULE=self.settings_module),) + args
        return self.vpy.settings(*newargs, **defaults)


class VirtualenvConf(object):
    """
    Configuration of a virtual python environment.
    One VirtualenvConf can hold multiple ProjectConfs.
    """
    def __init__(self, ssh_user, vpy_path, vpy_user, requirements, site_packages, projects):
        # type: (Optional[unicode], unicode, Optional[unicode], Dict[unicode, LooseVersion], List[unicode], List[ProjectConf]) -> None
        self.vpy_path = vpy_path
        self.vpy_user = vpy_user
        self.ssh_user = ssh_user
        self.requirements = requirements
        self.projects = projects
        self.site_packages = site_packages
        # self.host will be set by HostConf.__init__()
        self.host = None  # type: HostConf
        for p in projects:
            p.vpy = self

    def __unicode__(self):
        return "%s:%s" % (self.host, self.vpy_path)

    @property
    def pip(self):
        # type: () -> unicode
        """
        returns the path to the pip executable in this virtualenv
        """
        return '%s/bin/pip' % self.vpy_path

    @property
    def python(self):
        # type: () -> unicode
        """
        returns the path to the python executable in this virtualenv
        """
        return '%s/bin/python' % self.vpy_path


    def get_installed_pkgs(self):
        # type: () -> Dict[unicode, LooseVersion]
        """
        Reads the list of installed packages (by calling pip in the virtualenv)
        :return: Returns a dict of package names to version numbers (as LooseVersion)
        """
        with self.settings():
            lines = self.run('%s freeze' % self.pip, quiet=True).split('\n')
            return _lines_to_requirements(lines)

    def get_pkgs_to_install(self, release_log, pyversion):
        # type: (ReleaseLog, PyVersionInfo) -> ToInstallResult
        """
        Finds the packages that should be installed on the target virtualenv.
        Also returns the packages that are missing in the local wheel repository
        and any packages with in the target virtualenv that are ahead of the repository.
        """
        installed = self.get_installed_pkgs()
        installable = ((pkg, release_log.get_latest(pkg), installed.get(pkg))
                       for pkg in (self.requirements.keys() + self.site_packages))
        installable = [(pkg, spec, spec.get_wheel(pyversion) if spec is not None else None, version)
                       for pkg, spec, version in installable]
        return ToInstallResult(
            installables=[wheel for pkg, spec, wheel, version in installable
                          if wheel is not None and (version is None or spec.version > version)],
            missing = [pkg for pkg, spec, wheel, version in installable
                       if wheel is None],
            ahead = [PkgSpec(pkg, unicode(version), wheel) for pkg, spec, wheel, version in installable
                     if wheel is not None and version is not None and spec.version < version]
        )

    def get_py_version(self):
        # type: () -> PyVersionInfo
        """
        Returns the Python Platform  of this virtualenv (actually, only python version)
        """
        with self.settings():
            r = self.run("%s --version" % self.python, pty=False, quiet=True)
            out = r.stdout + r.stderr
            interpreter, version = out.split(" ", 2)
            v = version.split('.')
            return PyVersionInfo(int(v[0]), int(v[1]))

    @property
    def wheels(self):
        # type: () -> unicode
        """
        Returns the path to the directory to upload the wheels to.
        :return:
        """
        return os.path.join(self.vpy_path, 'wheels')

    def settings(self, *args, **kwargs):
        """
        context manager like fabric's settings, initialized to deal with this virtualenv.
        Sets host_string, use_ssh_config, connection_attempts, shell
        :param args: see fabric
        :param kwargs: see fabric
        """
        defaults = dict(host_string="%s@%s" % (self.ssh_user, self.host.hostname),
                        use_ssh_config=True,
                        connection_attempts=3,
                        shell='/bin/bash -c')
        # TODO: use_ssh_config and connection_attempts should be moved to the caller.
        if self.vpy_user != self.ssh_user:
            defaults["sudo_user"] = self.vpy_user
            print("settings sudo_user:", self.vpy_user)
        defaults.update(kwargs)
        return fabric.context_managers.settings(*args, **defaults)

    @classmethod
    def run(cls, cmd, *args, **kwargs):
        """
        Unified command execution - calls fabric's local(), run() or sudo operation() as required.
        Sets shell_escape to False - this is necessary to support remotes with a csh on login.
        Caller needs to set env via settings().
        :param cmd: the command to execute
        """
        from fabric.state import env
        from fabric.operations import run, sudo, local
        if env.get("host_string").endswith('@localhost'):
            return local(cmd, capture=True)
        # this is necessary to work with csh on login
        cmd = "\"'%s'\"" % cmd
        if env.get("sudo_user") in (None, env.get("user")):
            return run(cmd, *args, shell_escape=False, **kwargs)
        else:
            return sudo(cmd, *args, shell_escape=False, **kwargs)

    def match(self, query):
        """
        Does this user match the user query?

        Supported query types:
        - hostname
        - "vpy_user@host"
        - "user@host:full_path_to_vpy"
        - "host:full_path_vpy"
        - ":full_path"
        - "user@"
        - "" (matching everything)
        """
        # type: (unicode) -> bool
        if '@' in query:
            user, query = query.split('@')
            if not self.vpy_user == user:
                return False
        if ':' in query:
            query, path = query.split(':')
            if not self.vpy_path ==  path:
                return False
        if query == '':
            return True
        return query == self.host.hostname

class HostConf(object):
    """
    Configuration of a host, that can comprise multiple virtual environments.
    """
    def __init__(self, hostname, reload_cmd, reload_once, vpys):
        # type: (unicode, Callable[[VirtualenvConf], unicode], bool, List[VirtualenvConf]) -> None
        """
        :param hostname: like used for calling ssh. Use 'localhost' for local virtualenvs
        :param reload_cmd: called after deployment. Could also be a command to start unit tests ...
        :param reload_once: call reload_cmd only once for all virtualenvs?
        :param vpys:
        """
        self.hostname = hostname
        self.reload_cmd = reload_cmd
        self.reload_once = reload_once
        self.vpys = vpys
        for v in vpys:
            v.host = self

    def __unicode__(self):
        return self.hostname

    def reload_webservices(self, vpys):
        # type: (List[VirtualEnvConf]) -> None
        if self.reload_once:
            vpys = vpys[:1]
        for vpy in vpys:
            with vpy.settings():
                vpy.run(self.reload_cmd(vpy))

# noinspection PyMethodMayBeStatic,PyMethodMayBeStatic
class LocalConf(object):
    """
    hooks and helpers for your local configuration
    """
    def __init__(self, workspace, wheels, vpy_path, release_log, all_vpys):
        # type: (unicode, unicode, unicode, ReleaseLog, List[VirtualenvConf) -> None
        self.workspace = workspace
        self.wheels = wheels
        self.vpy_path = vpy_path
        self.release_log = release_log
        self.all_vpys = all_vpys

    @property
    def pip(self):
        # type: () -> unicode
        """
        Path to a local pip
        """
        return os.path.join(self.vpy_path, 'bin/pip')

    def task_deploy(self, vpy_names=""):
        # type: (unicode) -> None
        vpy_name_list = vpy_names.split(",")
        vpys = [v for v in self.all_vpys if any(v.match(vpy_name) for vpy_name in vpy_name_list)]
        updated_vpys = set()

        for vpy in vpys:
            try:
                print("\nUpdating %s" % unicode(vpy))
                with vpy.settings(remote_interrupt=True):
                    pyversion = vpy.get_py_version()
                    to_install, missing, ahead = vpy.get_pkgs_to_install(self.release_log, pyversion)
                    print("Zu installieren: %s" % ", ".join(unicode(p) for p in to_install))
                    if ahead:
                        warn('Packages ahead of repository: %s' % ', '.join(unicode(s) for s in ahead))
                    if missing:
                        warn('skipping %s: missing packages: %s' % (vpy, (", ".join(missing))))
                        raise Skip()
                    if not to_install:
                        print("Nichts zu installieren.")
                        raise Skip()
                    confirm = prompt('update? [j/n]')
                    if confirm.lower() not in ('j', 'y'):
                        raise Skip()
                    updated_vpys.add(vpy)
                    r = vpy.run('mkdir -p %s' % vpy.wheels)
                    if not r.succeeded:
                        self.release_log.abort(vpy, 'cannot create wheel directory')
                    for i, wheel in enumerate(to_install):
                        if vpy.host.hostname == 'localhost':
                            remote_path = os.path.join(self.wheels, wheel)
                        else:
                            remote_path = os.path.join(vpy.wheels, wheel)
                            r = put(local_path=os.path.join(self.wheels, wheel),
                                    remote_path=remote_path,
                                    use_sudo=vpy.ssh_user != vpy.vpy_user)
                            if not r.succeeded:
                                self.release_log.abort(vpy, 'could not put %s' % wheel)
                        r = vpy.run("%s install --upgrade %s" % (vpy.pip, remote_path))
                        if not r.succeeded:
                            self.release_log.abort(vpy, 'could not install %s after installing %s' % (
                            wheel, ", ".join(p.wheel for p in to_install[:i])))
                        self.release_log.add_install(vpy, wheel)
                    for proj in vpy.projects:
                        if proj.migrate:
                            with proj.settings():
                                r = vpy.run("%s migrate $DJANGO_SETTINGS_MODULE" % os.path.join(vpy.vpy_path, "bin",
                                                                                            "django_admin.py"))
                                if not r.succeeded:
                                    self.release_log.log_error(vpy,
                                                                    'could not migrate in %s after installing %s' % (
                                                                        proj,
                                                                        ", ".join(p.wheel for p in to_install)))
                    for wheel in to_install:
                        self.release_log.add_install(vpy, wheel)
            except Skip:
                pass
            for host in set(vpy.host for vpy in updated_vpys):
                with vpy.settings():
                    host.reload_webservices([v for v in vpys if v.host == host])

    def task_add_wheel(self, *pathnames):
        # type: (*unicode) -> None
        for path in pathnames:
            if path.endswith('.whl'):
                basepath = basename(path)
                target_path = os.path.join(self.wheels, basepath)
                print(target_path)
                if os.path.exists(target_path):
                    warn('wheel %s already exists, ignoring' % basepath)
                else:
                    pkg, version, _ = basepath.split("-", 2)
                    existing_pkg = self.release_log.get_latest(pkg)
                    if existing_pkg is not None:
                        if LooseVersion(version) < existing_pkg.version:
                            warn('wheel %s is out of date, ignoring' % basepath)
                            return
                        elif LooseVersion(version) == existing_pkg.version:
                            py_version = get_platform_tags(basepath)
                            if any(py_version in v for v, w in existing_pkg.wheels):
                                warn('wheel %s already in repository, ignoring' % basepath)
                                return
                    copy(path, target_path)
                    pkg = pkg.replace('_', '-')
                    self.release_log.add_release(pkg, version, basepath)
            else:
                warn('Ignoring non-wheel-file %s' % path)


class PkgRepository(Dict[unicode, PkgSpecList]):
    """
    This objects manages the wheel repository cache.
    Key is the package name, value the PkgSpecList.

    It is managed through the ReleaseLog, which takes care to persist changes.
    Do not call directly.
    """
    def add_wheel(self, pkg, version, wheel):
        # type: (unicode, unicode, unicode) -> bool
        """
        adds a package to me if it is newer than the existing package or
        if it has the same version.

        returns whether it was added
        """
        old = self.get(pkg)  #
        if old is None or LooseVersion(version) > old.version:
            self[pkg] = PkgSpecList(pkg, version, [wheel])
            return True
        elif LooseVersion(version) == old.version:
            self[pkg].add_wheel(wheel)
            return True
        return False


class ReleaseLog(object):
    """
    Manages the release log file that logs which packages are in the wheel directory
    and when they have been deployed to which environment.
    """
    def __init__(self, path):
        # type: (unicode) -> None
        self.path = path
        self.latest_pkg = self._read_entries()

    def _read_entries(self):
        # type: () -> PkgRepository
        """
        reads the entries from the release log
        :return:
        """
        latest_pkg = PkgRepository()
        with open(self.path, "r") as f:
            for l in f.readlines():
                if l.startswith('release:'):
                    tag, spec, wheel, stamp = l.strip().split(" ",3)
                    pkg, version = spec.split('==')
                    latest_pkg.add_wheel(pkg, version, wheel)
        return latest_pkg

    def add_release(self, pkg, version, wheel):
        # type (unicode, unicode, unicode) -> None
        """
        adds a package to the release log (and the wheel cache).
        The caller must place the wheel file into the wheel directory.
        """
        now = datetime.datetime.now()
        now.isoformat()
        with open(self.path, "a") as f:
            f.write(("release: %s==%s %s at %s\n" % (pkg, version, wheel, now.isoformat())).encode('utf-8'))
        self.latest_pkg.add_wheel(pkg, version, wheel)


    def add_install(self, vpy, wheel):
        # type (VirtualenvConf, PkgSpec) -> None
        """
        Writes a notice into the release log that a package has been deployed to a virtualenv
        """
        now = datetime.datetime.now()
        now.isoformat()
        with open(self.path, "a") as f:
            f.write(("install: %s: %s at %s\n" % (vpy, wheel, now.isoformat())).encode('utf-8'))

    @staticmethod
    def _error_message(tag, vpy, msg):
        # type: (unicode, VirtualenvConf, unicode) -> unicode
        """
        Formats an error message for the release log.
        :param tag: "error" or "aborting
        :param vpy: In which virtualenv it occurred
        :param msg: the message
        """
        return "%s: %s: %s\n" % (tag, vpy, msg)

    def log_error(self, vpy, msg):
        # type: (VirtualenvConf, msg) -> None
        """
        Logs an error message into the release log
        :return:
        """
        msg = ReleaseLog._error_message("error", vpy, msg)
        with open(self.path, "a") as f:
            f.write(msg.encode('utf-8', errors='replace'))
        fabric.utils.error(msg)

    def abort(self, vpy, msg):
        # type: (VirtualenvConf, msg) -> None
        """
        Logs an error message about a problem causing aborting into the release log and aborts.
        """
        msg = ReleaseLog._error_message("aborting", vpy, msg)
        with open(self.path, "a") as f:
            f.write(msg.encode('utf-8', errors='replace'))
            fabric.utils.abort(msg)

    def get_latest(self, pkg):
        # type: (unicode) -> Optional[PkgSpecList]
        """
        Looks up the latest version for the given package in the wheel cache
        :param pkg: Name of the package
        """
        return self.latest_pkg.get(pkg)



