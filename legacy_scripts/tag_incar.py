# script called by future and manager on login node
# major function: get tags from INCAR file and update INCAR file with given tags
# respect to the original INCAR file, if specific tags are satisfied

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

tagInfo = {
    "soc": {"default": False, "related": ["LSORBIT"]},
    "hse0": {"default": False, "related": ["HFSCREEN", "LHFCALC"]},
    "pbe0": {"default": False, "related": ["LHFCALC"]},
    "hyperfine": {"default": False, "related": ["LHYPERFINE"]},
    "pbe": {"default": False, "related": ["GGA"]},
    "pbesol": {"default": False, "related": ["GGA"]},
    "scan": {"default": False, "related": ["METAGGA"]},
    "spin": {"default": False, "related": ["ISPIN"]},
    "nelect": {"default": None, "related": ["NELECT"]},
    "nosym": {"default": False, "related": ["ISYM"]},
    "phonon": {"default": False, "related": ["IBRION"]},
    "relax2": {"default": False, "related": ["IBRION"]},
    "relax3": {"default": False, "related": ["IBRION"]},
}


# we need to convert tags like e=200, relax(relax=True) to a dictionary {e:200,relax:True} for further processing.
def convertTagsToDict(tags):
    _tags = {}
    for tag in tags:
        if "=" in tag:
            key, value = tag.split("=")
            try:
                value = float(value)
                if value.is_integer():
                    value = int(value)
            except:
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
            _tags[key] = value
        else:
            _tags[tag] = True
    return _tags


# modify tags interactively
def modifyTagsInteractively(tags, silent=False):
    confirm = False
    while True:
        if not confirm:
            confirm = input("Confirm? ([y]es or Enter/Others): ")
            confirm = confirm.lower() in ["y", "yes", ""]
        if confirm:
            break
        else:
            _tags = convertTagsToDict(input("Enter tags: ").split(" "))
            tags.update(_tags)
    return tags


class Incar:
    def __init__(self, incarAsString):
        lines = incarAsString.strip().replace(";", "\n").split("\n")
        self.incarAsDict = {}
        for i in lines:
            i = i.strip()
            if "=" in i and i[0] != "#":
                key, value = i.split("=")
                value = value.split("#")[0]
                key = key.strip()
                value = value.strip()
                try:
                    value = float(value)
                    if value.is_integer():
                        value = int(value)
                except:
                    if value.lower() in ["true", ".true.", "t"]:
                        value = True
                    elif value.lower() in ["false", ".false.", "f"]:
                        value = False
                self.incarAsDict[key] = value

    def save(self):
        incarAsString = ""
        for key, value in self.incarAsDict.items():
            incarAsString += f"{key} = {value}\n"
        return incarAsString

    def getTags(self, silent=False):
        # There are two kind of tags, INCAR tags and cmd tags. cmd tags should be more general and can be converted to INCAR tags.

        tagDict = {}
        tagDict["soc"] = (
            self.incarAsDict["LSORBIT"]
            if "LSORBIT" in self.incarAsDict
            else tagInfo["soc"]["default"]
        )
        tagDict["nosym"] = (
            self.incarAsDict["ISYM"] in [0, -1]
            if "ISYM" in self.incarAsDict
            else tagInfo["nosym"]["default"]
        )
        tagDict["hyperfine"] = (
            self.incarAsDict["LHYPERFINE"]
            if "LHYPERFINE" in self.incarAsDict
            else tagInfo["hyperfine"]["default"]
        )
        tagDict["pbe"] = (
            self.incarAsDict["GGA"] == "PE"
            if "GGA" in self.incarAsDict
            else tagInfo["pbe"]["default"]
        )
        tagDict["pbesol"] = (
            self.incarAsDict["GGA"] == "PS"
            if "GGA" in self.incarAsDict
            else tagInfo["pbesol"]["default"]
        )
        tagDict["scan"] = (
            "SCAN" in self.incarAsDict["METAGGA"]
            if "METAGGA" in self.incarAsDict
            else tagInfo["scan"]["default"]
        )
        tagDict["hse0"] = (
            self.incarAsDict["LHFCALC"] and self.incarAsDict["HFSCREEN"] > 0
            if ("LHFCALC" in self.incarAsDict and "HFSCREEN" in self.incarAsDict)
            else tagInfo["hse0"]["default"]
        )
        tagDict["pbe0"] = (
            self.incarAsDict["LHFCALC"]
            and (
                "HFSCREEN" not in self.incarAsDict
                or self.incarAsDict["HFSCREEN"] == 0.0
            )
            if "LHFCALC" in self.incarAsDict
            else tagInfo["pbe0"]["default"]
        )
        if "ISPIN" in self.incarAsDict:
            tagDict["spin"] = self.incarAsDict["ISPIN"] == 2
            if "NUPDOWN" in self.incarAsDict:
                tagDict["spin"] = self.incarAsDict["NUPDOWN"]
        else:
            tagDict["spin"] = tagInfo["spin"]["default"]
        tagDict["nelect"] = (
            self.incarAsDict["NELECT"]
            if "NELECT" in self.incarAsDict
            else tagInfo["nelect"]["default"]
        )
        tagDict["phonon"] = (
            self.incarAsDict["IBRION"] in [5, 6, 7, 8]
            if "IBRION" in self.incarAsDict
            else tagInfo["phonon"]["default"]
        )

        if "IBRION" in self.incarAsDict:
            if "ISIF" in self.incarAsDict:
                tagDict["relax2"] = self.incarAsDict["IBRION"] in [1, 2, 3] and self.incarAsDict["ISIF"]==2
                tagDict["relax3"] = self.incarAsDict["IBRION"] in [1, 2, 3] and self.incarAsDict["ISIF"]==3
            else:
                tagDict["relax2"] = self.incarAsDict["IBRION"] in [1, 2, 3]
                tagDict["relax3"] = False
        else:
            tagDict["relax2"] = tagInfo["relax2"]["default"]
            tagDict["relax3"] = tagInfo["relax3"]["default"]

        tagList = [key for key in tagDict if tagDict[key] != tagInfo[key]["default"]]

        if "nelect" in tagList:
            tagList.remove("nelect")
            tagList.append(f"nelect={tagDict['nelect']}")
        if "spin" in tagList and type(tagDict["spin"]) in [int, float]:
            tagList.remove("spin")
            tagList.append(f"spin={tagDict['spin']}")

        if tagList and not silent:
            print(f"Tags in INCAR file: {RED}{' '.join(tagList)}{RESET}")

        return {"dict": tagDict, "list": tagList}

    def _update(self, tags, silent=False):
        # remove unknown tags
        unknownTags = [key for key in tags if key not in tagInfo]
        if unknownTags and not silent:
            print(f"Unknown tags: {RED}{' '.join(unknownTags)}{RESET}")
        for key in unknownTags:
            del tags[key]

        # tag changes
        _tags = self.getTags(silent=True)["dict"]
        for key in _tags:
            if key not in tags:
                tags[key] = _tags[key]
        changedTags = {
            key: {"new": tags[key], "old": _tags[key]}
            for key in tags
            if tags[key] != _tags[key]
        }

        # incar changes
        oldIncar = self.incarAsDict.copy()

        if "soc" in changedTags:
            self.incarAsDict["LSORBIT"] = changedTags["soc"]["new"]

        if "nosym" in changedTags:
            self.incarAsDict["ISYM"] = -1 if changedTags["nosym"]["new"] else None

        if "hyperfine" in changedTags:
            self.incarAsDict["LHYPERFINE"] = changedTags["hyperfine"]["new"]

        if tags["pbe"]:
            if "pbe" in changedTags:
                self.incarAsDict["GGA"] = "PE"
        if tags["pbesol"]:
            if "pbesol" in changedTags:
                self.incarAsDict["GGA"] = "PS"
        if not tags["pbe"] and not tags["pbesol"]:
            self.incarAsDict["GGA"] = None

        if "scan" in changedTags:
            self.incarAsDict["METAGGA"] = (
                "r2SCAN" if changedTags["scan"]["new"] else None
            )

        if tags["hse0"]:
            if "hse0" in changedTags:
                self.incarAsDict["LHFCALC"] = True
                self.incarAsDict["HFSCREEN"] = 0.2
                self.incarAsDict["ALGO"] = "All"
                self.incarAsDict["PRECFOCK"] = "Fast"
        if tags["pbe0"]:
            if "pbe0" in changedTags:
                self.incarAsDict["LHFCALC"] = True
                self.incarAsDict["HFSCREEN"] = None
                self.incarAsDict["ALGO"] = "All"
                self.incarAsDict["PRECFOCK"] = "Fast"
        if not tags["hse0"] and not tags["pbe0"]:
            self.incarAsDict["LHFCALC"] = None

        if "spin" in changedTags:
            if type(changedTags["spin"]["new"]) in [int, float]:
                self.incarAsDict["ISPIN"] = 2
                self.incarAsDict["NUPDOWN"] = changedTags["spin"]["new"]
            elif changedTags["spin"]["new"]:
                self.incarAsDict["ISPIN"] = 2
                if "NUPDOWN" in self.incarAsDict:
                    self.incarAsDict["NUPDOWN"] = None
            else:
                self.incarAsDict["ISPIN"] = None
                self.incarAsDict["NUPDOWN"] = None

        if "nelect" in changedTags:
            self.incarAsDict["NELECT"] = changedTags["nelect"]["new"]

        if tags["phonon"]:
            if "phonon" in changedTags:
                self.incarAsDict["IBRION"] = 6
                self.incarAsDict["NSW"] = 1
                self.incarAsDict["ISIF"] = 3
        
        if tags["relax2"]:
            if "relax2" in changedTags:
                self.incarAsDict["IBRION"] = 2
                self.incarAsDict["ISIF"] = 2
                self.incarAsDict["NSW"] = 25
        
        if tags["relax3"]:
            if "relax3" in changedTags:
                self.incarAsDict["IBRION"] = 2
                self.incarAsDict["ISIF"] = 3
                self.incarAsDict["NSW"] = 25

        if not tags["phonon"] and not tags["relax2"] and not tags["relax3"]:
            self.incarAsDict["IBRION"] = None
            self.incarAsDict["NSW"] = None

        changedIncar = {
            key: {"new": self.incarAsDict[key], "old": oldIncar[key]}
            for key in self.incarAsDict
            if key in oldIncar and self.incarAsDict[key] != oldIncar[key]
        }

        # remove empty tags
        for key in list(self.incarAsDict):
            if self.incarAsDict[key] is None:
                del self.incarAsDict[key]

        changedIncar.update(
            {
                key: {"new": self.incarAsDict[key], "old": None}
                for key in self.incarAsDict
                if key not in oldIncar
            }
        )

        # print old in red and new in green
        if changedTags and not silent:
            print("Changed tags:")
            for key in changedTags:
                print(
                    f"{key}: {RED}{changedTags[key]['old']}{RESET} -> {GREEN}{changedTags[key]['new']}{RESET}"
                )

        if changedIncar and not silent:
            print("Changed INCAR:")
            for key in changedIncar:
                print(
                    f"{key}: {RED}{changedIncar[key]['old']}{RESET} -> {GREEN}{changedIncar[key]['new']}{RESET}"
                )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Using tags to edit INCAR file.")

    with open("INCAR", "r") as f:
        incarAsString = f.read()
    incar = Incar(incarAsString)

    print(f"available tags:{RED}{' '.join(sorted(list(tagInfo.keys())))}{RESET}")
    incar.getTags()

    parser.add_argument(
        "tags",
        nargs="*",
        default=[],
        type=str,
        help="specify the features of the job by tags.",
    )

    tags = convertTagsToDict(parser.parse_args().tags)

    incar._update(tags)

    # interactive mode
    while True:
        tags = incar.getTags()["dict"]
        tags = modifyTagsInteractively(tags, silent=False)
        incar._update(tags)
