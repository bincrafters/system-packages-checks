import os
from pathlib import Path

import yaml


def append_to_file(content: str, filename: Path) -> None:
    file_exists = filename.is_file()
    with filename.open("a", encoding="latin_1") as text_file:
        if not file_exists:
            url = "/".join([os.getenv("GITHUB_SERVER_URL", ""),
                            os.getenv("GITHUB_REPOSITORY", ""),
                            "actions",
                            "runs",
                            os.getenv("GITHUB_RUN_ID", ""),
                           "attempts",
                            os.getenv("GITHUB_RUN_ATTEMPT", "")])
            text_file.write("page generated on {{ site.time | date_to_xmlschema }} ")
            text_file.write(f"during [this run]({url})\n\n")
        text_file.write(content)


def createReport() -> None:
    res: dict[str, dict[str, dict[str, tuple[int, str]]]] = {}
    for file_name in Path.cwd().glob("artifact_*.yml"):
        with file_name.open("rt", encoding="latin_1") as f:
            d = yaml.safe_load(f)

        if d["pr"] not in res:
            res[d["pr"]] = {}

        if d["package"] not in res[d["pr"]]:
            res[d["pr"]][d["package"]] = {}

        res[d["pr"]][d["package"]][d["distro"]] = (d["res"], d["url"])

    distros = sorted({d for pr_ in res.values() for package_ in pr_.values() for d in package_})

    pages_folder = Path("pages")
    pages_folder.mkdir(exist_ok=True)
    pr_folder = pages_folder / "pr"
    pr_folder.mkdir(exist_ok=True)
    includes_folder = pages_folder / "_includes"
    includes_folder.mkdir(exist_ok=True)
    for pr in sorted(res):
        if pr == "0":
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
                elif res[pr][package][d][0] == 0:
                    md += f" [Success]({res[pr][package][d][1]}) |"
                elif res[pr][package][d][0] == 6:
                    md += f" [Not supported]({res[pr][package][d][1]}) |"
                else:
                    md += f" ***[Failure {res[pr][package][d][0]}]({res[pr][package][d][1]})*** |"
            md += "\n"
        md += "\n"
        print(md)
        with (includes_folder / f"{pr}.md").open("w", encoding="latin_1") as text_file:
            text_file.write(md)
        md = f"{{% include {pr}.md %}}\n"
        append_to_file(md, pr_folder / f"{pr}.md")
        append_to_file(md, pages_folder / "index.md")


if __name__ == "__main__":
    createReport()
