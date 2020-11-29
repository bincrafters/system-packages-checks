import os
import json
import yaml
import sys


class MatrixGenerator:
    owner = "conan-io"
    repo = "conan-center-index"

    def __init__(self, token=None, user=None, password=None):
        self.token = token
        self.user = user
        self.pw = password

    def generate_matrix(self):
        res = []
        install_python = {
            "opensuse/tumbleweed": "zypper --non-interactive install python3 python3-pip python3-setuptools python3-wheel tar gzip gcc-c++ make",
            "opensuse/leap":       "zypper --non-interactive install python3 python3-pip python3-setuptools python3-wheel tar gzip gcc-c++ make",
            "debian:10": "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "debian:9":  "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "ubuntu:hirsute": "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "ubuntu:groovy":  "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "ubuntu:focal":   "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "ubuntu:bionic":  "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "ubuntu:xenial":  "apt-get update && apt-get -qq install -y --no-install-recommends python3-pip python3-setuptools pkg-config g++ make",
            "centos:8":  "yum -y install dnf-plugins-core && yum config-manager --set-enabled PowerTools && yum install -y python3 python3-wheel python3-pip pkgconf-pkg-config gcc-c++ make",
            "archlinux": "pacman -Syu --noconfirm python-pip gcc pkgconf gcc make",
            "fedora:33": "dnf -y install python3 python3-wheel python3-pip pkgconf-pkg-config gcc-c++ make",
            "fedora:32": "dnf -y install python3 python3-wheel python3-pip pkgconf-pkg-config gcc-c++ make",
            "fedora:31": "dnf -y install python3 python3-wheel python3-pip pkgconf-pkg-config gcc-c++ make",
        }
        root_folder = os.path.join("CCI", "recipes")
        for package in os.listdir(root_folder):         
            filepath = os.path.join(root_folder, package, "config.yml")
            if not os.path.isfile(filepath):
                continue
            with open(filepath) as file:
                config = yaml.safe_load(file)
                if "system" not in config["versions"]:
                    continue
            for container in install_python:
                    res.append({
                        'package': package,
                        'distro': container,
                        'repo': '%s/%s' % (self.owner, self.repo),
                        'ref': 'master',
                        'folder': config["versions"]["system"]["folder"],
                        'install-python': install_python[container],
                    })

        print(json.dumps({"include": res}))

                



def main():
    d = MatrixGenerator(token=os.getenv("GH_TOKEN"))
    d.generate_matrix()


if __name__ == "__main__":
    # execute only if run as a script
    main()
