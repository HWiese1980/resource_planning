import yaml

from replan.logging import log

__all__=["Config", "Project", "Mapping", "ProjectDict", "ProductivityMapping", "ProductivityMappingDict"]


class YamlBase(yaml.YAMLObject):
    @classmethod
    def from_yaml(cls, loader, node, *args, **kwargs):
        fields = loader.construct_mapping(node, deep = True)
        yield cls(**fields)

    def __init__(self, *args, **kwargs):
        for attr in kwargs:
            val = kwargs[attr]
            log.debug("YAML Base %s: set Attribute %s -> %s" % (self.__class__.__name__, attr, val))
            setattr(self, attr, val)


class Config(YamlBase):
    yaml_tag = u"!Config"


class Project(YamlBase):
    yaml_tag = u"!Project"

    def __init__(self, code, name, ccenter, max = 1.0, ezve_ignore = False):
        super(Project, self).__init__()
        self.code = code
        self.name = name
        self.ccenter = ccenter
        self.max = max
        self.ezve_ignore = ezve_ignore

    def __repr__(self):
        return f"Project: [{self.code}] [{self.name}] [{self.ccenter}] [{self.max}] [EZVE: {'no' if self.ezve_ignore else 'yes'}]"


class Mapping(YamlBase):
    yaml_tag = u"!Mapping"

    def __init__(self, productive_project, fraction = 1.0):
        super(Mapping, self).__init__()
        self.productive_project = productive_project
        self.fraction = fraction

    def __repr__(self):
        return f"Map to {self.productive_project}"


class ProjectDict(YamlBase):
    yaml_tag = u"!ProjectDict"

    def __init__(self, definitions):
        super(ProjectDict, self).__init__()
        self.definitions = definitions

    def get_by_name(self, name):
        ret = [s for s in self.definitions if s.name == name]
        if not any(ret):
            p = Project(
                code = "empty",
                name = "empty",
                ccenter = "0"
            )
            p.name = name
            p.code = name.lower()
            p.ccenter = 0
            return p

        assert len(ret) == 1, f"There's more than one project named {name}"
        return ret[0]

    def get_by_code(self, code):
        ret = [s for s in self.definitions if s.code == code]
        if not any(ret):
            p = Project(
                code="empty",
                name="empty",
                ccenter="0"
            )
            p.name = code
            p.code = code.lower()
            p.ccenter = 0
            return p
    
        assert len(ret) == 1, f"There's more than one project with code {code}"
        return ret[0]
    
    def get_by_ccenter(self, ccenter):
        ret = [s for s in self.definitions if s.ccenter == ccenter]
        if ccenter <= 0 or not any(ret):
            p = Project()
            p.name = ccenter
            p.code = ccenter
            p.ccenter = 0
            return p
        assert len(ret) == 1, f"There's more than one project with ccenter {ccenter}"
        return ret[0]

    def __getitem__(self, name):
        return self.get_by_name(name)


class ProductivityMapping(YamlBase):
    yaml_tag = u"!PMapping"

    def __init__(self, code, mappings):
        super(ProductivityMapping, self).__init__()
        self.code = code
        self.mappings = mappings

    def __repr__(self):
        return f"Mappings for {self.code}: {', '.join([str(s) for s in self.mappings])}"


class ProductivityMappingDict(YamlBase):
    yaml_tag = u"!PMappingDict"

    def __getitem__(self, i):
        ret = [s for s in self.mappings if s.code == i]
        assert len(ret) <= 1, f"There's more than one mapping for project {i}"
        return ret[0]

    def __iter__(self):
        return self.mappings.__iter__()