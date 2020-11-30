import os
import json
import yaml
import requests
import subprocess
import shutil
from multiprocessing import Pool

def _get_diff(pr):
    r = requests.get(pr["diff_url"])
    r.raise_for_status()
    return r.text

class MatrixGenerator:
    owner = "conan-io"
    repo = "conan-center-index"

    dry_run = True

    def __init__(self, token=None, user=None, password=None):
        self.token = token
        self.user = user
        self.pw = password

        self.prs = {}

        page = 1
        while True:
            r = self._make_request("GET", f"/repos/{self.owner}/{self.repo}/pulls", params={
                "state": "open",
                "sort": "created",
                "direction": "desc",
                "per_page": 100,
                "page": str(page)
            })
            results = r.json()
            for p in results:
                self.prs[int(p["number"])] = p
            page += 1
            if not results:
                break

        with Pool(os.cpu_count()) as p:
            status_futures = {}
            for pr in self.prs:
                status_futures[pr] = p.apply_async(_get_diff, (self.prs[pr],))
            for pr in self.prs:
                self.prs[pr]["diff"] = status_futures[pr].get()

        for p in self.prs.values():
            p["libs"] = set()
            for line in p["diff"].split("\n"):
                if line.startswith("+++ b/recipes/") or line.startswith("--- a/recipes/"):
                    p["libs"].add(line.split("/")[2])

    def _make_request(self, method, url, **kwargs):
        if self.dry_run and method in ["PATCH", "POST"]:
            return
        headers = {}
        if self.token:
            headers["Authorization"] = "token %s" % self.token

        headers["Accept"] = "application/vnd.github.v3+json"

        auth = None
        if self.user and self.pw:
            auth = requests.auth.HTTPBasicAuth(self.user, self.pw)
        r = requests.request(method, "https://api.github.com" + url, headers=headers, auth=auth, **kwargs)
        r.raise_for_status()
        return r

    def generate_matrix(self):
        res = []

        def _add_package(package, repo, ref, root_folder, pr = "0"):
            filepath = os.path.join(root_folder, package, "config.yml")
            if not os.path.isfile(filepath):
                return
            with open(filepath) as file:
                config = yaml.safe_load(file)
                if "system" not in config["versions"]:
                    return
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
            for container in install_python:
                res.append({
                    'package': package,
                    'distro': container,
                    'repo': repo,
                    'ref': ref,
                    'folder': config["versions"]["system"]["folder"],
                    'install-python': install_python[container],
                    'pr': pr,
                })
                
        root_folder = os.path.join("CCI", "recipes")
        for package in os.listdir(root_folder):
            _add_package(package, '%s/%s' % (self.owner, self.repo), 'master', root_folder)

        for pr in self.prs.values():
            pr_number = str(pr["number"])
            subprocess.run(["git", "clone", "--depth", "1", "--no-checkout", "-b", pr["head"]["ref"], pr["head"]["repo"]["html_url"], pr_number], capture_output=True)
            os.chdir(pr_number)
            subprocess.run(["git", "sparse-checkout", "init", "--cone"], capture_output=True)
            for package in pr['libs']:
                subprocess.run(["git", "sparse-checkout", "set", os.path.join("recipes", package)], capture_output=True)
                _add_package(package, pr["head"]["repo"]["full_name"], pr["head"]["ref"], "recipes", pr_number)
            os.chdir("..")
            shutil.rmtree(pr_number)
                


        print(json.dumps({"include": res}))

                



def main():
    d = MatrixGenerator(token=os.getenv("GH_TOKEN"))
    d.generate_matrix()


if __name__ == "__main__":
    # execute only if run as a script
    main()
