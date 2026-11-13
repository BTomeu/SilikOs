# A small JSON Schema validator (draft-07), standard library only: enough for the official schemas of SPDX 2.3 and
# CycloneDX 1.6 that tests/test_sbom.py holds silik's bills to (tests/data/sbom/). The keywords those schemas use:
# type, enum, const, properties, required, additionalProperties, patternProperties, items (one schema or a list),
# additionalItems, minItems, maxItems, uniqueItems, minLength, maxLength, pattern, minimum, maximum, allOf, anyOf,
# oneOf, not, if / then / else, $ref (inside the file and to another file of the same folder), format (date-time is
# checked; the others, iri-reference, idn-email and uri, are not). A keyword it does not know stops the check
# (Unsupported) instead of passing in silence.
import json
import os
import re

KNOWN = {"type", "enum", "const", "properties", "required", "additionalProperties", "patternProperties", "items",
         "additionalItems", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength", "pattern", "minimum", "maximum",
         "allOf", "anyOf", "oneOf", "not", "if", "then", "else", "$ref", "format", "definitions", "$defs",
         # words that say, and do not check
         "title", "description", "$comment", "examples", "default", "$id", "$schema", "deprecated", "readOnly", "meta:enum"}
DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


class Unsupported(Exception):
    pass


class Validator:
    def __init__(self, path):
        self.dir = os.path.dirname(os.path.abspath(path))
        self.docs = {}
        self.root = self.doc(os.path.basename(path))
        self.name = os.path.basename(path)

    def doc(self, name):
        if name not in self.docs:
            with open(os.path.join(self.dir, name), encoding="utf-8") as f:
                self.docs[name] = json.load(f)
        return self.docs[name]

    def resolve(self, ref, name):
        """the schema a $ref names, and the file it is in"""
        file, _, frag = ref.partition("#")
        name = os.path.basename(file) if file else name      # (the schemas name each other by file name)
        node = self.doc(name)
        for part in [p for p in frag.split("/") if p]:
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node, name

    def validate(self, value):
        """the list of what is wrong ("path: reason"); empty when VALUE is valid"""
        errs = []
        self.check(value, self.root, self.name, "$", errs)
        return errs

    def ok(self, value, schema, name):
        errs = []
        self.check(value, schema, name, "$", errs)
        return not errs

    def check(self, v, s, name, at, errs):
        if s is True or s == {}:
            return
        if s is False:
            errs.append("%s: nothing is allowed here" % at)
            return
        for k in s:
            if k not in KNOWN:
                raise Unsupported("%s: the keyword %r of %s" % (at, k, name))
        if "$ref" in s:
            t, n = self.resolve(s["$ref"], name)
            self.check(v, t, n, at, errs)
        if "type" in s:
            ts = s["type"] if isinstance(s["type"], list) else [s["type"]]
            if not any(self.is_type(v, t) for t in ts):
                errs.append("%s: is not %s" % (at, " or ".join(ts)))
                return
        if "enum" in s and v not in s["enum"]:
            errs.append("%s: %r is not one of the %d allowed values" % (at, v, len(s["enum"])))
        if "const" in s and v != s["const"]:
            errs.append("%s: is not %r" % (at, s["const"]))
        if isinstance(v, str):
            if "minLength" in s and len(v) < s["minLength"]:
                errs.append("%s: shorter than %d" % (at, s["minLength"]))
            if "maxLength" in s and len(v) > s["maxLength"]:
                errs.append("%s: longer than %d" % (at, s["maxLength"]))
            if "pattern" in s and not re.search(s["pattern"], v):
                errs.append("%s: %r does not match %s" % (at, v, s["pattern"]))
            if s.get("format") == "date-time" and not DATE_TIME.match(v):
                errs.append("%s: %r is not a date-time" % (at, v))
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if "minimum" in s and v < s["minimum"]:
                errs.append("%s: below %s" % (at, s["minimum"]))
            if "maximum" in s and v > s["maximum"]:
                errs.append("%s: above %s" % (at, s["maximum"]))
        if isinstance(v, list):
            if "minItems" in s and len(v) < s["minItems"]:
                errs.append("%s: fewer than %d items" % (at, s["minItems"]))
            if "maxItems" in s and len(v) > s["maxItems"]:
                errs.append("%s: more than %d items" % (at, s["maxItems"]))
            if s.get("uniqueItems"):
                seen = set()
                for x in v:
                    key = json.dumps(x, sort_keys=True)
                    if key in seen:
                        errs.append("%s: an item is there twice: %s" % (at, key[:80]))
                        break
                    seen.add(key)
            items = s.get("items")
            if isinstance(items, list):
                for i, x in enumerate(v):
                    if i < len(items):
                        self.check(x, items[i], name, "%s[%d]" % (at, i), errs)
                    elif "additionalItems" in s:
                        self.check(x, s["additionalItems"], name, "%s[%d]" % (at, i), errs)
            elif items is not None:
                for i, x in enumerate(v):
                    self.check(x, items, name, "%s[%d]" % (at, i), errs)
        if isinstance(v, dict):
            props, pats = s.get("properties", {}), s.get("patternProperties", {})
            for r in s.get("required", []):
                if r not in v:
                    errs.append("%s: %r is missing" % (at, r))
            for k, x in v.items():
                known = False
                if k in props:
                    known = True
                    self.check(x, props[k], name, "%s.%s" % (at, k), errs)
                for pat, t in pats.items():
                    if re.search(pat, k):
                        known = True
                        self.check(x, t, name, "%s.%s" % (at, k), errs)
                if not known and "additionalProperties" in s:
                    if s["additionalProperties"] is False:
                        errs.append("%s: the property %r is not allowed" % (at, k))
                    else:
                        self.check(x, s["additionalProperties"], name, "%s.%s" % (at, k), errs)
        for t in s.get("allOf", []):
            self.check(v, t, name, at, errs)
        if "anyOf" in s and not any(self.ok(v, t, name) for t in s["anyOf"]):
            errs.append("%s: matches none of anyOf" % at)
        if "oneOf" in s:
            n = sum(1 for t in s["oneOf"] if self.ok(v, t, name))
            if n != 1:
                errs.append("%s: matches %d of oneOf, not one" % (at, n))
        if "not" in s and self.ok(v, s["not"], name):
            errs.append("%s: matches what it must not" % at)
        if "if" in s:
            branch = s.get("then") if self.ok(v, s["if"], name) else s.get("else")
            if branch is not None:
                self.check(v, branch, name, at, errs)

    @staticmethod
    def is_type(v, t):
        if t == "integer":
            return isinstance(v, int) and not isinstance(v, bool) or isinstance(v, float) and v.is_integer()
        if t == "number":
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        return isinstance(v, TYPES[t])
