"""The City's development applications table (CKAN): every application with its status and its point as NAD27 MTM
X/Y, read whole without the long descriptions and links; the descriptions and links of the few a build places are
asked for afterwards by FOLDERRSN. Both are kept for the day (ckan.read). Ported from BHPlus
bh_context/sources/devapps.py."""
from . import ckan

RESOURCE = "8907d8ed-c515-4ce9-b674-9f8c6eefcf0d"
WHAT = "development applications table"
FIELDS = ("APPLICATION#", "APPLICATION_TYPE", "STATUS", "DATE_SUBMITTED", "X", "Y", "FOLDERRSN", "STREET_NUM",
          "STREET_NAME", "STREET_TYPE", "STREET_DIRECTION")


def get_table(net, today):
    """Every row, read in row-id order so the pages neither skip nor repeat a row; an empty table is refused."""
    return ckan.none_is_wrong(ckan.read(net, RESOURCE, WHAT, today, fields=FIELDS, sort="_id", nonempty=True), WHAT)


def descriptions(net, folders, today):
    """{FOLDERRSN: (description, link)} for the applications `folders` names: the first text that says something
    and the first link, each "" when the City gives none."""
    if not folders:
        return {}
    wanted = sorted(folders)
    rows = ckan.read(net, RESOURCE, WHAT, today, filters={"FOLDERRSN": wanted},
                     fields=("FOLDERRSN", "DESCRIPTION", "APPLICATION_URL"))
    texts, links = {}, {}
    for row in rows:
        folder = row.get("FOLDERRSN")
        if not isinstance(folder, str):
            continue
        text, link = row.get("DESCRIPTION"), row.get("APPLICATION_URL")
        if isinstance(text, str) and text.strip() and folder not in texts:
            texts[folder] = text.strip()
        if isinstance(link, str) and link.strip() and folder not in links:
            links[folder] = link.strip()
    return {folder: (texts.get(folder, ""), links.get(folder, "")) for folder in wanted}
