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
            distros = {
                "opensuse/tumbleweed",
                "opensuse/leap",
                "debian:10",
                "debian:9",
                "ubuntu:hirsute",
                "ubuntu:groovy",
                "ubuntu:focal",
                "ubuntu:bionic",
                "ubuntu:xenial",
                "centos:8",
                "archlinux",
                "fedora:33",
                "fedora:32",
                "fedora:31",
            }
            for distro in distros:
                res.append({
                    'package': package,
                    'distro': distro,
                    'repo': repo,
                    'ref': ref,
                    'folder': config["versions"]["system"]["folder"],
                    'pr': pr,
                })
                
        root_folder = os.path.join("CCI", "recipes")
        for package in os.listdir(root_folder):
            _add_package(package, '%s/%s' % (self.owner, self.repo), 'master', root_folder)

        for pr in self.prs.values():
            pr_number = str(pr["number"])
            subprocess.run(["git", "clone", "--depth", "1", "--no-checkout", "-b", pr["head"]["ref"], pr["head"]["repo"]["html_url"], pr_number], check=True)
            os.chdir(pr_number)
            subprocess.run(["git", "sparse-checkout", "init", "--cone"], check=True)
            for package in pr['libs']:
                subprocess.run(["git", "sparse-checkout", "set", os.path.join("recipes", package)], check=True)
                subprocess.run(["git", "checkout"], check=True)
                _add_package(package, pr["head"]["repo"]["full_name"], pr["head"]["ref"], "recipes", pr_number)
            os.chdir("..")
            shutil.rmtree(pr_number)
                


        with open("matrix.yml", "w") as f:
            json.dump({"include": res}, f)

                



def main():
    d = MatrixGenerator(token=os.getenv("GH_TOKEN"))
    d.generate_matrix()


if __name__ == "__main__":
    # execute only if run as a script
    main()
