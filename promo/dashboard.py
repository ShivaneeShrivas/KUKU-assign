import json, os
HERE = os.path.dirname(__file__)
def write_dashboard(payload, path):
    tpl = open(os.path.join(HERE, "dashboard_template.html"), encoding="utf-8").read() if os.path.exists(os.path.join(HERE, "dashboard_template.html")) else "__DATA__"
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    open(path, "w", encoding="utf-8").write(tpl.replace("__DATA__", data))
