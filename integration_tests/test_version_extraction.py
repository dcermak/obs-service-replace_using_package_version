import pytest

from pytest_container import DerivedContainer

from replace_using_package_version.replace_using_package_version import (
    __doc__ as pkg_doc,
)

TESTFILE = "/opt/testfile"

CONTAINERFILE = rf"""RUN zypper -n in python3-pip find && zypper -n download apache2 python3
WORKDIR /.build-srcdir/
COPY dist/*whl /opt/
RUN pip install /opt/*whl
RUN echo $'This is a testfile with some replacements like %%MINOR%%\n\
%NEVR%\n\
and a footer?' > {TESTFILE}

# remove the signkeys to mimic the state in OBS workers
RUN rpm -qa|grep '^gpg-pubkey'|xargs rpm -e
RUN mkdir -p /.build-srcdir/repos/ && mv $(find /var/cache/zypp/ -name 'apache*') /.build-srcdir/repos/

RUN mkdir /.build/ && echo $'RECIPEFILE="Dockerfile"\n\
BUILD_JOBS="12"\n\
BUILD_ARCH="x86_64:i686:i586:i486:i386"\n\
BUILD_RPMS=""\n\
BUILD_DIST="/.build/build.dist"' > /.build/build.data

RUN echo $'FROM registry.opensuse.org/opensuse/tumbleweed\n\
LABEL VERSION="%%VERSION%%"' > /.build-srcdir/Dockerfile

ENV BUILD_DIST="/.build/build.dist"
"""

TUMBLEWEED = DerivedContainer(
    base="registry.opensuse.org/opensuse/tumbleweed", containerfile=CONTAINERFILE
)
LEAP = DerivedContainer(
    base="registry.opensuse.org/opensuse/leap:15.3", containerfile=CONTAINERFILE
)
SLE = DerivedContainer(
    base="registry.suse.com/suse/sle15:15.3", containerfile=CONTAINERFILE
)


CONTAINER_IMAGES = [TUMBLEWEED, LEAP, SLE]


def test_help_works(auto_container):
    assert (
        pkg_doc.strip()
        in auto_container.connection.run_expect(
            [0], "replace_using_package_version -h"
        ).stdout.strip()
    )


def test_failure_when_file_non_existent(auto_container):
    fname = "/opt/non_existent"
    assert (
        f"File {fname} not found"
        in auto_container.connection.run_expect(
            [1],
            fr"replace_using_package_version --file {fname} --outdir /opt/ --regex='footer' --package=apache2",
        ).stderr
    )


def test_failure_when_outdir_non_existent(auto_container):
    dirname = "/opt/non_existent"
    assert (
        f"Output directory {dirname} not found"
        in auto_container.connection.run_expect(
            [1],
            fr"replace_using_package_version --file {TESTFILE} --outdir {dirname} --regex='footer' --package=apache2",
        ).stderr
    )


def test_failure_when_invalid_parse_version(auto_container):
    assert (
        "Invalid value for this flag."
        in auto_container.connection.run_expect(
            [1],
            fr"replace_using_package_version --file {TESTFILE} --outdir /opt/ --regex='footer' --package='zypper' --parse-version='foobar'",
        ).stderr
    )


def test_basic_replacement(auto_container_per_test):
    auto_container_per_test.connection.run_expect(
        [0],
        f"replace_using_package_version --file {TESTFILE} --outdir /opt/ --regex='footer' --parse-version='major' --replacement='header'",
    )
    assert (
        auto_container_per_test.connection.file(TESTFILE)
        .content_string.strip()
        .split("\n")[-1]
        == "and a header?"
    )


@pytest.mark.parametrize("version,index", [("major", 0), ("minor", 1), ("patch", 2)])
def test_version_replacement(auto_container_per_test, version: str, index: int):
    auto_container_per_test.connection.run_expect(
        [0],
        f"replace_using_package_version --file {TESTFILE} --outdir /opt/ --regex='%NEVR%' --package='zypper' --parse-version='{version}'",
    )
    assert auto_container_per_test.connection.file(
        TESTFILE
    ).content_string.strip().split("\n")[1] == ".".join(
        auto_container_per_test.connection.run_expect(
            [0], "rpm -q --qf '%{version}' zypper"
        )
        .stdout.strip()
        .split(".")[: index + 1]
    )


@pytest.mark.parametrize("version,index", [("major", 0), ("minor", 1), ("patch", 2)])
def test_version_replacement_from_local_file(
    auto_container_per_test, version: str, index: int
):
    auto_container_per_test.connection.run_expect(
        [0],
        f"replace_using_package_version --file {TESTFILE} --outdir /opt/ --regex='%NEVR%' --package='apache2' --parse-version='{version}'",
    )

    apache2_ver = auto_container_per_test.connection.run_expect(
        [0],
        "rpm -q --qf '%{version}' /.build-srcdir/repos/*rpm",
    ).stdout.strip()

    assert auto_container_per_test.connection.file(
        TESTFILE
    ).content_string.strip().split("\n")[1] == ".".join(
        apache2_ver.split(".")[: index + 1]
    )


def test_replacement_from_default_build_recipe(auto_container_per_test):
    auto_container_per_test.connection.run_expect(
        [0],
        f"replace_using_package_version --outdir /opt/ --regex='%%VERSION%%' --package='apache2'",
    )
    apache2_ver = auto_container_per_test.connection.run_expect(
        [0],
        "rpm -q --qf '%{version}' /.build-srcdir/repos/*rpm",
    ).stdout.strip()

    assert (
        auto_container_per_test.connection.file(
            "/opt/Dockerfile"
        ).content_string
        == f"""FROM registry.opensuse.org/opensuse/tumbleweed\n\
LABEL VERSION="{apache2_ver}"
"""
    )
