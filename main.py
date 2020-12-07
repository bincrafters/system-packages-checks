import os
import json
import yaml
import requests
from multiprocessing import Pool

def _get_diff(pr):
    r = requests.get(pr["diff_url"])
    r.raise_for_status()
    return r.text


def _add_package(package, repo, ref, pr = "0"):
    r = requests.get("https://raw.githubusercontent.com/%s/%s/recipes/%s/config.yml" % (repo, ref, package))
    if r.status_code == requests.codes.not_found:
        folder = "system"
        r = requests.get("https://raw.githubusercontent.com/%s/%s/recipes/%s/%s/conanfile.py" % (repo, ref, package, folder))
        if r.status_code == requests.codes.not_found:
            print("no system folder found for package %s in pr %s %s" % (package, pr, r.url))
            return None
        r.raise_for_status()
    else:
        r.raise_for_status()
        config = yaml.safe_load(r.text)
        if "system" not in config["versions"]:
            return None
        folder = config["versions"]["system"]["folder"]
    return {
            'package': package,
            'repo': repo,
            'ref': ref,
            'folder': folder,
            'pr': pr,
        }

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
                
        r = self._make_request("GET", f"/repos/{self.owner}/{self.repo}/contents/recipes")

        
        with Pool(os.cpu_count()) as p:
            status_futures = []
            for package in  r.json():
                status_futures.append(p.apply_async(_add_package, (package['name'], '%s/%s' % (self.owner, self.repo), 'master',)))

            for pr in self.prs.values():
                pr_number = str(pr["number"])
                for package in pr['libs']:
                    status_futures.append(p.apply_async(_add_package, (package, pr["head"]["repo"]["full_name"], pr["head"]["ref"], pr_number,)))

            res = []
            for f in status_futures:
                c = f.get()
                if c is None:
                    continue
                for distro in {"opensuse/tumbleweed",
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
                            }:
                    c['distro'] = distro
                    res.append(c)



        with open("matrix.yml", "w") as f:
            json.dump({"include": res}, f)

                



def main():
    d = MatrixGenerator(token=os.getenv("GH_TOKEN"))
    d.generate_matrix()


if __name__ == "__main__":
    # execute only if run as a script
    main()
