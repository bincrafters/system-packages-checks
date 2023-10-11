# pylint: disable = invalid-name, too-few-public-methods

import os
import json
import copy
import urllib.parse
import asyncio
import logging
from datetime import datetime
from typing import Set, Dict, List
import aiohttp
import yaml
import requests


class MatrixGenerator:
    owner: str = "conan-io"
    repo: str = "conan-center-index"
    dry_run: bool = False

    def __init__(self, token: str = "", user: str = "", pw: str = ""):  # noqa: MC0001
        self.session = requests.session()
        if token:
            self.session.headers["Authorization"] = f"token {token}"

        self.session.headers["Accept"] = "application/vnd.github.v3+json"
        self.session.headers["User-Agent"] = "request"

        self.session.auth = None
        if user and pw:
            self.session.auth = requests.auth.HTTPBasicAuth(user, pw)

        self.prs = {}
        return

        page = 1
        while True:
            r = self._make_request("GET", f"/repos/{self.owner}/{self.repo}/pulls",
                                   params={"state": "open",
                                           "sort": "created",
                                           "direction": "desc",
                                           "per_page": 100,
                                           "page": str(page)})
            r.raise_for_status()
            results = r.json()
            for p in results:
                self.prs[int(p["number"])] = p
            page += 1
            if not results:
                break

        for pr_number, pr in self.prs.items():
            pr["libs"] = self._get_modified_libs_for_pr(pr_number)

    def _get_modified_libs_for_pr(self, pr: int) -> Set[str]:
        res: Set[str] = set()
        for file in self._make_request("GET", f"/repos/{self.owner}/{self.repo}/pulls/{pr}/files").json():
            parts = file['filename'].split("/")
            if len(parts) >= 4 and parts[0] == "recipes":
                res.add(f"{parts[1]}/{parts[2]}")
        return res

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        if self.dry_run and method in ["PATCH", "POST"]:
            return requests.Response()

        r = self.session.request(method, f"https://api.github.com{url}", **kwargs)
        r.raise_for_status()
        if int(r.headers["X-RateLimit-Remaining"]) < 10:
            logging.warning("%s/%s github api call used, remaining %s until %s",
                            r.headers["X-Ratelimit-Used"], r.headers["X-RateLimit-Limit"], r.headers["X-RateLimit-Remaining"],
                            datetime.fromtimestamp(int(r.headers["X-Ratelimit-Reset"])))
        return r

    async def generate_matrix(self) -> None:  # noqa: MC0001
        res: List[Dict[str, str]] = []

        async with aiohttp.ClientSession() as session:

            async def _add_package(package: str, repo: str, ref: str, pr: str = "0") -> None:
                refs = package.split("/")
                package = refs[0]
                modified_folder = refs[1] if len(refs) >= 2 else ""
                async with session.get(f"https://raw.githubusercontent.com/{repo}/{ref}/recipes/{package}/config.yml") as r:
                    if r.status == 404:
                        folder = "system"
                        if modified_folder and modified_folder != folder:
                            return
                        async with session.get(f"https://raw.githubusercontent.com/{repo}/{ref}/recipes/{package}/{folder}/conanfile.py") as r:
                            if r.status == 404:
                                logging.warning("no system folder found for package %s in pr %s %s", package, pr, r.url)
                                return
                            r.raise_for_status()
                    else:
                        r.raise_for_status()
                        try:
                            config = yaml.safe_load(await r.text())
                        except yaml.YAMLError as exc:
                            logging.warning("Error in configuration file:%s, %s, %s, %s, %s", package, repo, ref, pr, exc)
                            return
                        if "system" not in config["versions"]:
                            return
                        folder = config["versions"]["system"]["folder"]
                        if modified_folder and modified_folder != folder:
                            return
                res.append({'package': package,
                            'repo': repo,
                            'ref': ref,
                            'folder': folder,
                            'pr': pr,
                            })
            tasks = []
            for package in os.listdir("CCI/recipes"):
                tasks.append(_add_package(package, f'{self.owner}/{self.repo}', 'master'))

            for pr in self.prs.values():
                pr_number = str(pr["number"])
                for package in pr['libs']:
                    if not pr["head"]["repo"]:
                        logging.warning("no repo detected for pr #%s", pr_number)
                        continue
                    tasks.append(_add_package(package, pr["head"]["repo"]["full_name"], urllib.parse.quote_plus(pr["head"]["ref"]), pr_number))

            await asyncio.gather(*tasks)

        job_id = 0
        for p in res:
            p["job_id"] = str(job_id)
            job_id += 1

        linux = []
        for p in res:
            for distro in ["opensuse/tumbleweed",
                           # "opensuse/leap", # does not have pipx
                           "debian:12",
                           "debian:10",
                           "ubuntu:jammy",
                           "ubuntu:focal",
                           "almalinux:8",
                           "almalinux:9",
                           "archlinux",
                           "fedora",
                           "quay.io/centos/centos:stream8",
                           # "quay.io/centos/centos:stream9", # does not have pipx
                           ]:
                config = copy.deepcopy(p)
                config['distro'] = distro
                linux.append(config)

        with open("matrixLinux.yml", "w", encoding="latin_1") as f:
            json.dump({"include": linux}, f)

        with open("matrixBSD.yml", "w", encoding="latin_1") as f:
            json.dump({"include": res}, f)


def main() -> None:
    d = MatrixGenerator(token=os.getenv("GH_TOKEN", ""))
    asyncio.run(d.generate_matrix())


if __name__ == "__main__":
    main()
