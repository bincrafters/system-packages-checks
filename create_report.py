import os
import yaml
from datetime import datetime, timezone

def append_to_file(content, filename):
    file_exists = os.path.isfile(filename)
    with open(filename, "a") as text_file:
        if not file_exists:
            text_file.write("{% include generation_date.md %}\n\n")
        text_file.write(content)

def createReport():
    res = dict()
    for file_name in os.listdir():
        if not file_name.startswith('artifact_'):
            continue
        with open(file_name, 'rt') as f:
            d = yaml.safe_load(f)

        if d['pr'] not in res:
            res[d['pr']] = dict()

        if d['package'] not in res[d['pr']]:
            res[d['pr']][d['package']] = dict()

        res[d['pr']][d['package']][d['distro']] = d['res']

    distros = list()

    for pr in res:
        for package in res[pr]:
            for d in res[pr][package]:
                if d not in distros:
                    distros.append(d)

    os.makedirs("pages", exist_ok=True)
    os.chdir("pages")
    os.makedirs("pr", exist_ok=True)
    os.makedirs("_includes", exist_ok=True)
    url = "/".join([os.getenv('GITHUB_SERVER_URL'), os.getenv('GITHUB_REPOSITORY'), 'actions', 'runs', os.getenv('GITHUB_RUN_ID')])
    with open("_includes/generation_date.md", "w") as text_file:
        text_file.write(f"page generated on {datetime.now(timezone.utc)} during [this run]({url})")
    for pr in res:
        if pr == 0:
            md = "\n# master\n\n"
        else:
            md = f"\n# [#{pr}](https://github.com/conan-io/conan-center-index/pull/{pr})\n\n"

        md += "| package |"
        for distro in distros:
            md += f" {distro} |"
        md += "\n"

        md += "| - |"
        for distro in distros:
            md += " - |"
        md += "\n"

        for package in res[pr]:
            md += f"| {package} |"
            for d in distros:
                if d not in res[pr][package]:
                    md += " Not run |"
                elif res[pr][package][d] == 0:
                    md += " Success |"
                else:
                    md += f" Failure {res[pr][package][d]} |"
            md += "\n"
        md += "\n"
        print(md)
        with open(f"_includes/{pr}.md", "w") as text_file:
            text_file.write(md)
        md = "{% include " + str(pr) + ".md %}\n"
        append_to_file(md, f"pr/{pr}.md")
        append_to_file(md, "index.md")


if __name__ == '__main__':
    createReport()
