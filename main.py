# pylint: disable = invalid-name, too-few-public-methods

import os
import json
import copy
import asyncio
import logging
from datetime import datetime
import aiohttp
import yaml


class MatrixGenerator:
    owner: str = "conan-io"
    repo: str = "conan-center-index"

    def __init__(self, session: aiohttp.ClientSession, token: str = "", user: str = "", pw: str = ""):  # noqa: MC0001
        self.session = session
        if token:
            self.session.headers["Authorization"] = f"token {token}"

        self.session.headers["Accept"] = "application/vnd.github.v3+json"
        self.session.headers["User-Agent"] = "request"

        if user and pw:
            self.session.headers["Authorization"] = aiohttp.encode_basic_auth(user, pw)

        self.prs = {}

    async def populate_prs(self):
        page = 1
        while True:
            async with self.session.get(f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls", params={"state": "open",
                                           "sort": "created",
                                           "direction": "desc",
                                           "per_page": 100,
                                           "page": str(page)}) as r:
                r.raise_for_status()
                if int(r.headers["X-RateLimit-Remaining"]) < 10:
                    logging.warning("%s/%s github api call used, remaining %s until %s",
                                    r.headers["X-Ratelimit-Used"], r.headers["X-RateLimit-Limit"], r.headers["X-RateLimit-Remaining"],
                                    datetime.fromtimestamp(int(r.headers["X-Ratelimit-Reset"])))
                results = await r.json()
            for p in results:
                self.prs[int(p["number"])] = p
            page += 1
            if not results:
                break

        for pr_number, libs in zip(self.prs, await asyncio.gather(*[
            self._get_modified_libs_for_pr(pr_number)
            for pr_number in self.prs
        ])):
            self.prs[pr_number]["libs"] = libs

    async def _get_modified_libs_for_pr(self, pr: int) -> set[str]:
        res: set[str] = set()
        
        async with self.session.get(f"https://api.github.com/repos/{self.owner}/{self.repo}/pulls/{pr}/files") as r:
            r.raise_for_status()
            if int(r.headers["X-RateLimit-Remaining"]) < 10:
                logging.warning("%s/%s github api call used, remaining %s until %s",
                                r.headers["X-Ratelimit-Used"], r.headers["X-RateLimit-Limit"], r.headers["X-RateLimit-Remaining"],
                                datetime.fromtimestamp(int(r.headers["X-Ratelimit-Reset"])))
            files = await r.json()
            
        for file in files:
            parts = file['filename'].split("/")
            if len(parts) >= 4 and parts[0] == "recipes":
                res.add(f"{parts[1]}/{parts[2]}")
        return res

    async def generate_matrix(self) -> None:  # noqa: MC0001
        res: list[dict[str, str]] = []

        async def _add_package(package: str, repo: str, ref: str, pr: str = "0") -> None:
            refs = package.split("/")
            package = refs[0]
            modified_folder = refs[1] if len(refs) >= 2 else ""
            async with self.session.get(f"https://raw.githubusercontent.com/{repo}/{ref}/recipes/{package}/config.yml") as r:
                if r.status == 404:
                    folder = "system"
                    if modified_folder and modified_folder != folder:
                        return
                    async with self.session.get(f"https://raw.githubusercontent.com/{repo}/{ref}/recipes/{package}/{folder}/conanfile.py") as r:
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
                    if "versions" not in config:
                        logging.warning("Config misses versions for %s", package)
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
                tasks.append(_add_package(package, f'{self.owner}/{self.repo}', pr["merge_commit_sha"], pr_number))

        await asyncio.gather(*tasks)

        linux = []
        for p in res:
            for distro in ["opensuse/tumbleweed",
                           "opensuse/leap",
                           "debian:stable",
                           "debian:oldstable",
                           "ubuntu:24.04",
                           "ubuntu:26.04",
                           "almalinux:9",
                           "almalinux:10",
                           "archlinux",
                           "fedora",
                           "quay.io/centos/centos:stream10",
                           "alpine:3.23",
                           ]:
                config = copy.deepcopy(p)
                config['distro'] = distro
                linux.append(config)

        with open("matrixLinux.yml", "w", encoding="latin_1") as f:
            json.dump({"include": linux}, f)

        with open("matrixBSD.yml", "w", encoding="latin_1") as f:
            json.dump({"include": res}, f)


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        d = MatrixGenerator(session, token=os.getenv("GH_TOKEN", ""))
        await d.populate_prs()
        await d.generate_matrix()


if __name__ == "__main__":
    asyncio.run(main())
