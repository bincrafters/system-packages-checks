import os
import json
import yaml
import requests
import asyncio, aiohttp
import copy
import urllib.parse

class MatrixGenerator:
    owner = "conan-io"
    repo = "conan-center-index"

    dry_run = True

    def __init__(self, token=None, user=None, pw=None):
        self.session = requests.session()
        self.session.headers = {}
        if token:
            self.session.headers["Authorization"] = "token %s" % token

        self.session.headers["Accept"] = "application/vnd.github.v3+json"
        self.session.headers["User-Agent"] = "request"

        self.session.auth = None
        if user and pw:
            self.session.auth = requests.auth.HTTPBasicAuth(user, pw)

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

        async def _populate_diffs():
            async with aiohttp.ClientSession() as session:
                async def _populate_diff(pr):
                    async with session.get(self.prs[pr]["diff_url"]) as r:
                        r.raise_for_status()
                        self.prs[pr]["libs"] = set()
                        try:
                            diff = await r.text()
                        except UnicodeDecodeError:
                            print("error when decoding diff at %s" % self.prs[pr]["diff_url"])
                            return
                        for line in diff.split("\n"):
                            if line.startswith("+++ b/recipes/") or line.startswith("--- a/recipes/"):
                                self.prs[pr]["libs"].add(line.split("/")[2])
                await asyncio.gather(*[asyncio.create_task(_populate_diff(pr)) for pr in self.prs])

        loop = asyncio.get_event_loop()
        loop.run_until_complete(_populate_diffs())

    def _make_request(self, method, url, **kwargs):
        if self.dry_run and method in ["PATCH", "POST"]:
            return

        r = self.session.request(method, "https://api.github.com" + url, **kwargs)
        r.raise_for_status()
        return r

    async def generate_matrix(self):
        res = []
                
        async with aiohttp.ClientSession() as session:

            async def _add_package(package, repo, ref, pr = "0"):
                async with session.get("https://raw.githubusercontent.com/%s/%s/recipes/%s/config.yml" % (repo, ref, package)) as r:
                    if r.status  == 404:
                        folder = "system"
                        async with session.get("https://raw.githubusercontent.com/%s/%s/recipes/%s/%s/conanfile.py" % (repo, ref, package, folder)) as r:
                            if r.status  == 404:
                                print("no system folder found for package %s in pr %s %s" % (package, pr, r.url))
                                return
                            r.raise_for_status()
                    else:
                        r.raise_for_status()
                        config = yaml.safe_load(await r.text())
                        if "system" not in config["versions"]:
                            return
                        folder = config["versions"]["system"]["folder"]
                res.append({
                        'package': package,
                        'repo': repo,
                        'ref': ref,
                        'folder': folder,
                        'pr': pr,
                    })
            tasks = []
            for package in  os.listdir("CCI/recipes"):
                tasks.append(asyncio.create_task(_add_package(package, '%s/%s' % (self.owner, self.repo), 'master')))

            for pr in self.prs.values():
                pr_number = str(pr["number"])
                for package in pr['libs']:
                    if not pr["head"]["repo"]:
                        print("no repo detected for pr #%s" % pr_number)
                        continue
                    tasks.append(asyncio.create_task(_add_package(package, pr["head"]["repo"]["full_name"], urllib.parse.quote_plus(pr["head"]["ref"]), pr_number)))

            await asyncio.gather(*tasks)

        linux = []
        for p in res:
            for distro in { # disabled until https://mobile.twitter.com/stabbbles/status/1440780481507692545 is fixed
                            #"opensuse/tumbleweed",
                            "opensuse/leap:15.2",
                            "debian:11",
                            "debian:10",
                            "debian:9",
                            "ubuntu:jammy",
                            "ubuntu:impish",
                            "ubuntu:hirsute",
                            "ubuntu:focal",
                            "ubuntu:bionic",
                            "almalinux:8.5",
                            "archlinux",                
                            "fedora:36",
                            "fedora:35",
                            "fedora:34",
                            "fedora:33",
                            "quay.io/centos/centos:stream8",
                            "quay.io/centos/centos:stream9",
                            }:
                config = copy.deepcopy(p)
                config['distro'] = distro
                linux.append(config)


        with open("matrixLinux.yml", "w") as f:
            json.dump({"include": linux}, f)


        with open("matrixBSD.yml", "w") as f:
            json.dump({"include": res}, f)
                


def main():
    d = MatrixGenerator(token=os.getenv("GH_TOKEN"))
    loop = asyncio.get_event_loop()
    loop.run_until_complete(d.generate_matrix())


if __name__ == "__main__":
    # execute only if run as a script
    main()
