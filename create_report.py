# pylint: disable = invalid-name, too-many-branches

import os
from typing import Dict, List
import yaml


def append_to_file(content: str, filename: str) -> None:
    file_exists = os.path.isfile(filename)
    with open(filename, "a", encoding="latin_1") as text_file:
        if not file_exists:
            url = "/".join([os.getenv('GITHUB_SERVER_URL', ''),
                            os.getenv('GITHUB_REPOSITORY', ''),
                            'actions',
                            'runs',
                            os.getenv('GITHUB_RUN_ID', '')])
            text_file.write("page generated on {{ site.time | date_to_xmlschema }} ")
            text_file.write(f"during [this run]({url})\n\n")
        text_file.write(content)


def createReport() -> None: # noqa: MC0001
    res: Dict[str, Dict[str, Dict[str, List[str]]]] = {}
    for file_name in os.listdir():
        if not file_name.startswith('artifact_'):
            continue
        with open(file_name, 'rt', encoding="latin_1") as f:
            d = yaml.safe_load(f)

        if d['pr'] not in res:
            res[d['pr']] = {}

        if d['package'] not in res[d['pr']]:
            res[d['pr']][d['package']] = {}

        res[d['pr']][d['package']][d['distro']] = d['res']

    distros = []

    for pr_ in res.values():
        for package_ in pr_.values():
            for d in package_:
                if d not in distros:
                    distros.append(d)
    distros.sort()

    os.makedirs("pages", exist_ok=True)
    os.chdir("pages")
    os.makedirs("pr", exist_ok=True)
    os.makedirs("_includes", exist_ok=True)
    for pr in sorted(res):
        if pr == 0:
            md = "\n# master\n\n"
        else:
            md = f"\n# [#{pr}](https://github.com/conan-io/conan-center-index/pull/{pr})\n\n"

        packages = sorted(res[pr])
        md += "|  |"
        md += "".join(f" {package} |" for package in packages)
        md += "\n"

        md += "| - |"
        md += "".join(" - |" for package in packages)
        md += "\n"

        for d in distros:
            md += f"| {d} |"
            for package in packages:
                if d not in res[pr][package]:
                    md += " Not run |"
                elif res[pr][package][d] == 0:
                    md += " Success |"
                elif res[pr][package][d] == 6:
                    md += " Not supported |"
                else:
                    md += f" ***Failure {res[pr][package][d]}*** |"
            md += "\n"
        md += "\n"
        print(md)
        with open(f"_includes/{pr}.md", "w", encoding="latin_1") as text_file:
            text_file.write(md)
        md = "{% include " + str(pr) + ".md %}\n"
        append_to_file(md, f"pr/{pr}.md")
        append_to_file(md, "index.md")


if __name__ == '__main__':
    createReport()
